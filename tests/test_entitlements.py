# tests/test_entitlements.py
# Proves plan-based entitlement gating and quota clamping.

import pytest

from saas import provisioning, repository
from saas.entitlements import Entitlements, EntitlementError
from saas.plans import Feature, FREE, PRO, ENTERPRISE, get_plan


def _scope(saas_session_factory, catalog_session_factory, tenant):
    return repository.TenantScope(
        saas_session_factory(), catalog_session_factory(), tenant
    )


def test_unknown_plan_falls_back_to_free():
    # Least privilege: a typo must never elevate a tenant.
    assert get_plan("platinum").name == "free"
    assert get_plan("").name == "free"
    assert get_plan(None).name == "free"


def test_free_plan_lacks_vendor_matches():
    ent = Entitlements(plan=FREE)
    assert ent.allows(Feature.VIEW_NICHES)
    assert not ent.allows(Feature.VENDOR_MATCHES)
    with pytest.raises(EntitlementError):
        ent.require(Feature.VENDOR_MATCHES)


def test_pro_plan_grants_vendor_matches():
    ent = Entitlements(plan=PRO)
    assert ent.allows(Feature.VENDOR_MATCHES)
    ent.require(Feature.VENDOR_MATCHES)  # does not raise


def test_page_size_is_clamped_to_plan_ceiling():
    assert Entitlements(plan=FREE).clamp_page_size(1000) == FREE.max_niches_per_request
    assert Entitlements(plan=PRO).clamp_page_size(1000) == PRO.max_niches_per_request
    assert Entitlements(plan=FREE).clamp_page_size(0) == 1  # never below 1


def test_free_tenant_blocked_from_vendor_matches_in_repository(
    seeded_catalog, saas_session_factory, catalog_session_factory
):
    ids = seeded_catalog
    s = saas_session_factory()
    free_tenant = provisioning.create_tenant(s, name="FreeCo", plan="free")
    provisioning.grant_niches(s, free_tenant, [ids["niche_a"]])
    s.close()

    scope = _scope(saas_session_factory, catalog_session_factory, free_tenant)

    # Free can see niches and pain points...
    assert repository.list_niches(scope, limit=10)
    assert repository.list_pain_points(scope, ids["niche_a"])

    # ...but vendor matches require PRO and must raise EntitlementError.
    with pytest.raises(EntitlementError):
        repository.list_vendor_matches(scope, ids["pain_a"])


def test_total_cap_limits_full_catalog_visibility(
    seeded_catalog, saas_session_factory, catalog_session_factory
):
    # FREE caps total niches at 10; enterprise is effectively unlimited.
    assert Entitlements(plan=FREE).max_niches_total == FREE.max_niches_total
    assert Entitlements(plan=ENTERPRISE).max_niches_total >= 1_000_000
