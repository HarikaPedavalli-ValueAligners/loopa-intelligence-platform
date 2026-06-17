# tests/test_tenant_isolation.py
# Proves per-tenant data isolation: a tenant can ONLY read niche markets (and
# their pain points / vendor matches) that were provisioned to it.

from saas import provisioning, repository
from saas.tenancy import Tenant


def _scope(saas_session_factory, catalog_session_factory, tenant):
    return repository.TenantScope(
        saas_session_factory(), catalog_session_factory(), tenant
    )


def test_scoped_tenant_sees_only_granted_niche(
    seeded_catalog, saas_session_factory, catalog_session_factory
):
    ids = seeded_catalog
    s = saas_session_factory()

    # Tenant A is on PRO (so vendor matches are allowed) and granted ONLY niche A.
    tenant_a = provisioning.create_tenant(s, name="Acme", plan="pro")
    provisioning.grant_niches(s, tenant_a, [ids["niche_a"]])
    s.close()

    scope = _scope(saas_session_factory, catalog_session_factory, tenant_a)

    niches = repository.list_niches(scope, limit=50)
    visible_ids = {n["id"] for n in niches}

    assert visible_ids == {ids["niche_a"]}
    assert ids["niche_b"] not in visible_ids


def test_tenant_cannot_read_unauthorized_niche_directly(
    seeded_catalog, saas_session_factory, catalog_session_factory
):
    ids = seeded_catalog
    s = saas_session_factory()
    tenant_a = provisioning.create_tenant(s, name="Acme", plan="pro")
    provisioning.grant_niches(s, tenant_a, [ids["niche_a"]])
    s.close()

    scope = _scope(saas_session_factory, catalog_session_factory, tenant_a)

    # Direct fetch of the OTHER tenant's niche must return None (not found).
    assert repository.get_niche(scope, ids["niche_b"]) is None
    # The granted niche is readable.
    assert repository.get_niche(scope, ids["niche_a"])["id"] == ids["niche_a"]


def test_pain_points_isolated(
    seeded_catalog, saas_session_factory, catalog_session_factory
):
    ids = seeded_catalog
    s = saas_session_factory()
    tenant_a = provisioning.create_tenant(s, name="Acme", plan="pro")
    provisioning.grant_niches(s, tenant_a, [ids["niche_a"]])
    s.close()

    scope = _scope(saas_session_factory, catalog_session_factory, tenant_a)

    # Pain points for the granted niche are visible.
    pps = repository.list_pain_points(scope, ids["niche_a"])
    assert pps and pps[0]["pain_point"] == "Ransomware"

    # Pain points for the un-granted niche are denied (None).
    assert repository.list_pain_points(scope, ids["niche_b"]) is None


def test_vendor_matches_cannot_be_pivoted_via_foreign_pain_point(
    seeded_catalog, saas_session_factory, catalog_session_factory
):
    ids = seeded_catalog
    s = saas_session_factory()
    tenant_a = provisioning.create_tenant(s, name="Acme", plan="pro")
    provisioning.grant_niches(s, tenant_a, [ids["niche_a"]])
    s.close()

    scope = _scope(saas_session_factory, catalog_session_factory, tenant_a)

    # Vendor matches for the tenant's own pain point are visible.
    own = repository.list_vendor_matches(scope, ids["pain_a"])
    assert own and own[0]["vendor_name"] == "ShieldCo"

    # Trying to read vendor matches for the OTHER tenant's pain point is denied,
    # even though we pass a valid pain_point_id.
    assert repository.list_vendor_matches(scope, ids["pain_b"]) is None


def test_new_tenant_sees_nothing_by_default(
    seeded_catalog, saas_session_factory, catalog_session_factory
):
    s = saas_session_factory()
    # No grants, not full_catalog -> empty visibility (safe default).
    tenant = provisioning.create_tenant(s, name="Fresh", plan="pro")
    s.close()

    scope = _scope(saas_session_factory, catalog_session_factory, tenant)
    assert repository.list_niches(scope, limit=50) == []


def test_full_catalog_tenant_sees_all(
    seeded_catalog, saas_session_factory, catalog_session_factory
):
    ids = seeded_catalog
    s = saas_session_factory()
    tenant = provisioning.create_tenant(s, name="BigCo", plan="enterprise",
                                        full_catalog=True)
    s.close()

    scope = _scope(saas_session_factory, catalog_session_factory, tenant)
    visible = {n["id"] for n in repository.list_niches(scope, limit=50)}
    assert visible == {ids["niche_a"], ids["niche_b"]}
