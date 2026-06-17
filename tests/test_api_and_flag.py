# tests/test_api_and_flag.py
# End-to-end tests over the HTTP API using Starlette's TestClient (no network,
# no uvicorn). Also proves the feature flag gate: OFF -> nothing exposed.

import pytest
from fastapi.testclient import TestClient

from saas import provisioning
from saas.api import create_api
from saas.app import build_app
from saas.config import SaaSConfig
from saas.ratelimit import RateLimiter


@pytest.fixture()
def api_client(seeded_catalog, saas_session_factory, catalog_session_factory):
    """A TestClient wired to temp DBs, with one PRO tenant + key provisioned."""
    ids = seeded_catalog

    # Provision a tenant and grant it only niche A.
    s = saas_session_factory()
    tenant = provisioning.create_tenant(s, name="Acme", plan="pro")
    minted = provisioning.issue_key(s, tenant)
    provisioning.grant_niches(s, tenant, [ids["niche_a"]])
    s.close()

    config = SaaSConfig(
        enabled=True, admin_token="test-admin-token",
        default_plan="free", free_rate_per_min=0,
    )
    app = create_api(
        config=config,
        saas_session_factory=saas_session_factory,
        data_session_factory=catalog_session_factory,
        rate_limiter=RateLimiter(),
    )
    client = TestClient(app)
    return client, minted.plaintext, ids


def _auth(key):
    return {"Authorization": f"Bearer {key}"}


def test_health_is_public(api_client):
    client, _key, _ids = api_client
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_unauthenticated_request_rejected(api_client):
    client, _key, _ids = api_client
    assert client.get("/api/v1/niches").status_code == 401


def test_me_returns_plan(api_client):
    client, key, _ids = api_client
    r = client.get("/api/v1/me", headers=_auth(key))
    assert r.status_code == 200
    body = r.json()
    assert body["plan"] == "pro"
    assert "vendor_matches" in body["features"]


def test_niches_scoped_to_grant(api_client):
    client, key, ids = api_client
    r = client.get("/api/v1/niches", headers=_auth(key))
    assert r.status_code == 200
    returned = {n["id"] for n in r.json()["niches"]}
    assert returned == {ids["niche_a"]}


def test_unauthorized_niche_is_404(api_client):
    client, key, ids = api_client
    r = client.get(f"/api/v1/niches/{ids['niche_b']}", headers=_auth(key))
    assert r.status_code == 404


def test_vendor_matches_flow(api_client):
    client, key, ids = api_client
    r = client.get(f"/api/v1/pain-points/{ids['pain_a']}/vendors", headers=_auth(key))
    assert r.status_code == 200
    assert r.json()["vendors"][0]["vendor_name"] == "ShieldCo"


def test_free_tenant_gets_402_on_vendor_matches(
    seeded_catalog, saas_session_factory, catalog_session_factory
):
    ids = seeded_catalog
    s = saas_session_factory()
    free_t = provisioning.create_tenant(s, name="FreeCo", plan="free")
    minted = provisioning.issue_key(s, free_t)
    provisioning.grant_niches(s, free_t, [ids["niche_a"]])
    s.close()

    config = SaaSConfig(enabled=True, admin_token="t", default_plan="free",
                        free_rate_per_min=0)
    app = create_api(config=config, saas_session_factory=saas_session_factory,
                     data_session_factory=catalog_session_factory)
    client = TestClient(app)

    r = client.get(f"/api/v1/pain-points/{ids['pain_a']}/vendors",
                   headers=_auth(minted.plaintext))
    assert r.status_code == 402
    assert r.json()["error"] == "upgrade_required"


def test_rate_limit_returns_429(
    seeded_catalog, saas_session_factory, catalog_session_factory
):
    ids = seeded_catalog
    s = saas_session_factory()
    # free plan default rate is 30/min; override to 2 for the test.
    t = provisioning.create_tenant(s, name="Slow", plan="free")
    minted = provisioning.issue_key(s, t)
    provisioning.grant_niches(s, t, [ids["niche_a"]])
    s.close()

    config = SaaSConfig(enabled=True, admin_token="t", default_plan="free",
                        free_rate_per_min=2)
    app = create_api(config=config, saas_session_factory=saas_session_factory,
                     data_session_factory=catalog_session_factory)
    client = TestClient(app)
    h = _auth(minted.plaintext)

    assert client.get("/api/v1/niches", headers=h).status_code == 200
    assert client.get("/api/v1/niches", headers=h).status_code == 200
    assert client.get("/api/v1/niches", headers=h).status_code == 429


def test_admin_requires_token(
    seeded_catalog, saas_session_factory, catalog_session_factory
):
    config = SaaSConfig(enabled=True, admin_token="secret-admin",
                        default_plan="free", free_rate_per_min=0)
    app = create_api(config=config, saas_session_factory=saas_session_factory,
                     data_session_factory=catalog_session_factory)
    client = TestClient(app)

    # No token -> 403.
    assert client.post("/api/v1/admin/tenants", json={"name": "X"}).status_code == 403
    # Wrong token -> 403.
    assert client.post(
        "/api/v1/admin/tenants", json={"name": "X"},
        headers={"Authorization": "Bearer nope"},
    ).status_code == 403
    # Correct token -> 200 and a new tenant id.
    r = client.post(
        "/api/v1/admin/tenants", json={"name": "X", "plan": "pro"},
        headers={"Authorization": "Bearer secret-admin"},
    )
    assert r.status_code == 200
    assert r.json()["tenant_id"].startswith("tnt_")


# ---------------------------------------------------------------------------
# Feature-flag gate
# ---------------------------------------------------------------------------

def test_flag_off_disables_everything():
    config = SaaSConfig(enabled=False, admin_token="", default_plan="free",
                        free_rate_per_min=0)
    app = build_app(config)
    client = TestClient(app)
    # Every path is 404 when the flag is OFF.
    assert client.get("/").status_code == 404
    assert client.get("/api/v1/health").status_code == 404
    assert client.get("/api/v1/niches").status_code == 404


def test_flag_on_serves_landing_and_api(
    saas_session_factory, catalog_session_factory
):
    config = SaaSConfig(enabled=True, admin_token="t", default_plan="free",
                        free_rate_per_min=0)
    app = build_app(config)
    client = TestClient(app)
    # Landing page renders, health responds.
    assert client.get("/").status_code == 200
    assert client.get("/api/v1/health").status_code == 200
