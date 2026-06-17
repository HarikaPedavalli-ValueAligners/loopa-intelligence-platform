# saas/plans.py
# Subscription plan tiers, feature entitlements, and quotas.
#
# This is the single source of truth for "what can a tenant on plan X do".
# It is pure data + pure functions: no I/O, no secrets, no database. That
# makes entitlement decisions deterministic and trivially testable.
#
# Three tiers ship by default:
#   free       - safe default; read-only, capped results, low rate limit
#   pro        - paying tenants; vendor matches + full reports, higher caps
#   enterprise - everything, generous caps
#
# Features are referenced by name (see Feature) so callers never branch on the
# raw plan string.

from dataclasses import dataclass, field
from typing import Dict, FrozenSet


class Feature:
    """Named feature flags that plans grant. Use these constants, not strings."""

    VIEW_NICHES = "view_niches"          # list/read niche market intelligence
    VIEW_PAIN_POINTS = "view_pain_points"  # read pain points per niche
    VENDOR_MATCHES = "vendor_matches"    # see matched vendors per pain point
    FULL_REPORT = "full_report"          # assemble the full sales report
    EXPORT = "export"                    # bulk/export-style access


@dataclass(frozen=True)
class Plan:
    """A subscription tier: which features it grants and its usage quotas."""

    name: str
    features: FrozenSet[str]
    # Max niche-market rows returnable in a single request.
    max_niches_per_request: int
    # Hard cap on niche rows the tenant may read at all (None = unlimited).
    max_niches_total: int
    # Per-tenant API rate limit, requests per minute.
    rate_per_min: int

    def has_feature(self, feature: str) -> bool:
        return feature in self.features

    def clamp_limit(self, requested: int) -> int:
        """Clamps a requested page size to this plan's per-request ceiling."""
        if requested is None or requested < 1:
            requested = 1
        return min(int(requested), self.max_niches_per_request)


# ---------------------------------------------------------------------------
# Plan catalog
# ---------------------------------------------------------------------------

FREE = Plan(
    name="free",
    features=frozenset({Feature.VIEW_NICHES, Feature.VIEW_PAIN_POINTS}),
    max_niches_per_request=5,
    max_niches_total=10,
    rate_per_min=30,
)

PRO = Plan(
    name="pro",
    features=frozenset({
        Feature.VIEW_NICHES,
        Feature.VIEW_PAIN_POINTS,
        Feature.VENDOR_MATCHES,
        Feature.FULL_REPORT,
    }),
    max_niches_per_request=50,
    max_niches_total=500,
    rate_per_min=120,
)

ENTERPRISE = Plan(
    name="enterprise",
    features=frozenset({
        Feature.VIEW_NICHES,
        Feature.VIEW_PAIN_POINTS,
        Feature.VENDOR_MATCHES,
        Feature.FULL_REPORT,
        Feature.EXPORT,
    }),
    max_niches_per_request=200,
    max_niches_total=1_000_000,  # effectively unlimited
    rate_per_min=600,
)


PLANS: Dict[str, Plan] = {
    FREE.name: FREE,
    PRO.name: PRO,
    ENTERPRISE.name: ENTERPRISE,
}

# The safe fallback used whenever a tenant references an unknown plan.
DEFAULT_PLAN_NAME = FREE.name


def get_plan(name: str) -> Plan:
    """
    Resolves a plan by name, falling back to the free tier for any unknown
    or empty value. This guarantees a tenant can never be accidentally
    elevated by a typo: unknown -> free (least privilege).
    """
    if not name:
        return FREE
    return PLANS.get(str(name).strip().lower(), FREE)
