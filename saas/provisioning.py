# saas/provisioning.py
# Admin/control-plane operations: create tenants, mint API keys, and provision
# per-tenant access to the shared catalog. These are the write operations of the
# SaaS control plane (they only ever touch the saas_* tables, never the legacy
# intelligence tables).
#
# Callers must hold the admin token (enforced at the API layer, see api.py).

from typing import Iterable, List

from saas.auth import MintedKey, mint_api_key
from saas.plans import get_plan
from saas.tenancy import Tenant, TenantNicheAccess, generate_tenant_id


def create_tenant(session, name: str, plan: str = "free",
                  full_catalog: bool = False) -> Tenant:
    """
    Creates a tenant on the given plan. Unknown plan names fall back to free
    (least privilege). New tenants start with NO catalog access unless
    full_catalog is explicitly set.
    """
    resolved_plan = get_plan(plan).name  # normalize/validate against catalog
    tenant = Tenant(
        tenant_id=generate_tenant_id(),
        name=name,
        plan=resolved_plan,
        full_catalog=bool(full_catalog),
        is_active=True,
    )
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    return tenant


def issue_key(session, tenant: Tenant, label: str = "") -> MintedKey:
    """Mints an API key for the tenant and commits it. Plaintext shown once."""
    minted = mint_api_key(session, tenant, label=label)
    session.commit()
    return minted


def grant_niches(session, tenant: Tenant, niche_ids: Iterable[int]) -> int:
    """
    Adds niche_market_id values to a tenant's allow-list (idempotent). Returns
    the number of NEW grants created. Has no effect on full_catalog tenants
    beyond recording explicit grants.
    """
    existing = {
        row.niche_market_id
        for row in session.query(TenantNicheAccess).filter(
            TenantNicheAccess.tenant_pk == tenant.id
        )
    }
    added = 0
    for nid in niche_ids:
        nid = int(nid)
        if nid in existing:
            continue
        session.add(TenantNicheAccess(tenant_pk=tenant.id, niche_market_id=nid))
        existing.add(nid)
        added += 1
    session.commit()
    return added


def revoke_niches(session, tenant: Tenant, niche_ids: Iterable[int]) -> int:
    """Removes niche grants from a tenant's allow-list. Returns rows removed."""
    ids = [int(n) for n in niche_ids]
    if not ids:
        return 0
    removed = (
        session.query(TenantNicheAccess)
        .filter(
            TenantNicheAccess.tenant_pk == tenant.id,
            TenantNicheAccess.niche_market_id.in_(ids),
        )
        .delete(synchronize_session=False)
    )
    session.commit()
    return removed


def set_plan(session, tenant: Tenant, plan: str) -> Tenant:
    """Changes a tenant's plan (validated against the catalog)."""
    tenant.plan = get_plan(plan).name
    session.commit()
    session.refresh(tenant)
    return tenant


def list_tenant_grants(session, tenant: Tenant) -> List[int]:
    """Returns the niche ids currently granted to a tenant."""
    return [
        row.niche_market_id
        for row in session.query(TenantNicheAccess).filter(
            TenantNicheAccess.tenant_pk == tenant.id
        )
    ]
