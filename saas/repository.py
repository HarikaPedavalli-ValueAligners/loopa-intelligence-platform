# saas/repository.py
# Tenant-scoped, READ-ONLY access to the existing market-intelligence catalog.
#
# This is where data isolation is enforced. Every query that returns shared-
# catalog data (niche markets, pain points, vendor matches) is constrained to
# the set of niche_market_id values the tenant is allowed to see:
#
#   - tenant.full_catalog == True  -> all niche ids are visible (plan-capped)
#   - tenant.full_catalog == False -> only ids present in saas_tenant_niche
#
# A tenant can therefore NEVER read a niche (or its pain points / vendor
# matches) that was not provisioned to it. Pain points and vendor matches are
# additionally re-checked against the allowed niche set so there is no way to
# pivot from an unauthorized pain_point_id back into data.
#
# This module imports the EXISTING schema (database.schema) unchanged and never
# writes to the legacy tables.

from typing import List, Optional, Set

from sqlalchemy import select

from database.schema import NicheMarket, PainPoint, Vendor, VendorPainPointMap
from saas.entitlements import Entitlements
from saas.plans import Feature
from saas.tenancy import Tenant, TenantNicheAccess


class TenantScope:
    """
    Resolves and caches the set of niche_market_id values visible to a tenant.

    Constructed from the SaaS control-plane session (for the allow-list) and the
    legacy intelligence session (the shared catalog being read).
    """

    def __init__(self, saas_session, data_session, tenant: Tenant):
        self.saas_session = saas_session
        self.data_session = data_session
        self.tenant = tenant
        self.entitlements = Entitlements.for_tenant(tenant)
        self._allowed_ids: Optional[Set[int]] = None

    def allowed_niche_ids(self) -> Set[int]:
        """
        Returns the set of niche_market_id values this tenant may read.

        For full_catalog tenants this is the full set of ids in the catalog,
        truncated to the plan's total cap. For scoped tenants it is exactly the
        provisioned allow-list (also truncated to the plan cap).
        """
        if self._allowed_ids is not None:
            return self._allowed_ids

        if self.tenant.full_catalog:
            rows = self.data_session.execute(
                select(NicheMarket.id).order_by(NicheMarket.priority_score.desc())
            ).all()
            ids = [r[0] for r in rows]
        else:
            rows = self.saas_session.execute(
                select(TenantNicheAccess.niche_market_id).where(
                    TenantNicheAccess.tenant_pk == self.tenant.id
                )
            ).all()
            ids = [r[0] for r in rows]

        cap = self.entitlements.max_niches_total
        self._allowed_ids = set(ids[:cap]) if cap and cap > 0 else set(ids)
        return self._allowed_ids

    def can_see_niche(self, niche_id: int) -> bool:
        return niche_id in self.allowed_niche_ids()


def list_niches(scope: TenantScope, limit: int = 5) -> List[dict]:
    """
    Returns the tenant's visible niche markets ranked by priority score.

    Requires the VIEW_NICHES feature. The page size is clamped to the plan's
    per-request ceiling and the result is restricted to allowed niche ids.
    """
    scope.entitlements.require(Feature.VIEW_NICHES)

    allowed = scope.allowed_niche_ids()
    if not allowed:
        return []

    page_size = scope.entitlements.clamp_page_size(limit)

    rows = scope.data_session.execute(
        select(NicheMarket)
        .where(NicheMarket.id.in_(allowed))
        .order_by(NicheMarket.priority_score.desc())
        .limit(page_size)
    ).scalars().all()

    return [
        {
            "id": n.id,
            "industry": n.industry,
            "sub_industry": n.sub_industry,
            "sub_sub_industry": n.sub_sub_industry,
            "niche_name": n.niche_name,
            "demand_score": n.demand_score,
            "outbound_score": n.outbound_score,
            "priority_score": n.priority_score,
            "priority_tier": n.priority_tier,
        }
        for n in rows
    ]


def get_niche(scope: TenantScope, niche_id: int) -> Optional[dict]:
    """Returns a single niche only if the tenant is allowed to see it."""
    scope.entitlements.require(Feature.VIEW_NICHES)

    if not scope.can_see_niche(niche_id):
        return None

    n = scope.data_session.get(NicheMarket, niche_id)
    if n is None:
        return None

    return {
        "id": n.id,
        "industry": n.industry,
        "sub_industry": n.sub_industry,
        "sub_sub_industry": n.sub_sub_industry,
        "niche_name": n.niche_name,
        "geography": n.geography,
        "naics_code": n.naics_code,
        "demand_score": n.demand_score,
        "outbound_score": n.outbound_score,
        "priority_score": n.priority_score,
        "priority_tier": n.priority_tier,
        "icp_headcount_min": n.icp_headcount_min,
        "icp_headcount_max": n.icp_headcount_max,
        "icp_description": n.icp_description,
        "common_cyber_risks": n.common_cyber_risks,
    }


def list_pain_points(scope: TenantScope, niche_id: int) -> Optional[List[dict]]:
    """
    Returns pain points for a niche, or None if the tenant cannot see the niche.

    Requires the VIEW_PAIN_POINTS feature. The niche check prevents reading pain
    points for an unauthorized niche.
    """
    scope.entitlements.require(Feature.VIEW_PAIN_POINTS)

    if not scope.can_see_niche(niche_id):
        return None

    rows = scope.data_session.execute(
        select(PainPoint)
        .where(PainPoint.niche_market_id == niche_id)
        .order_by(PainPoint.pain_point_rank)
    ).scalars().all()

    return [
        {
            "id": pp.id,
            "rank": pp.pain_point_rank,
            "pain_point": pp.pain_point_name,
            "category": pp.cyber_category,
            "subcategory": pp.cyber_subcategory,
            "severity": pp.severity_score,
            "growth_rate": pp.growth_rate,
            "description": pp.description,
        }
        for pp in rows
    ]


def list_vendor_matches(scope: TenantScope, pain_point_id: int, limit: int = 3):
    """
    Returns vendor matches for a pain point, gated by the VENDOR_MATCHES feature
    AND by whether the tenant may see the pain point's parent niche.

    Returns None when the tenant cannot see the underlying niche (isolation),
    and raises EntitlementError when the plan lacks the vendor-match feature.
    """
    scope.entitlements.require(Feature.VENDOR_MATCHES)

    pp = scope.data_session.get(PainPoint, pain_point_id)
    if pp is None:
        return None

    # Re-anchor to the niche allow-list: no pivoting via pain_point_id.
    if not scope.can_see_niche(pp.niche_market_id):
        return None

    matches = scope.data_session.execute(
        select(VendorPainPointMap)
        .where(VendorPainPointMap.pain_point_id == pain_point_id)
        .order_by(VendorPainPointMap.match_score.desc())
        .limit(limit)
    ).scalars().all()

    results = []
    for m in matches:
        v = scope.data_session.get(Vendor, m.vendor_id)
        if v is None:
            continue
        results.append({
            "vendor_name": v.vendor_name,
            "cyber_category": v.cyber_category,
            "target_market": v.target_market,
            "customer_rating": v.customer_rating,
            "match_score": m.match_score,
            "notes": m.notes,
        })
    return results
