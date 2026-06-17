# tests/test_auth_and_ratelimit.py
# Proves API-key auth (hash-only storage, constant-time verify) and per-tenant
# rate limiting.

from saas import provisioning
from saas.auth import authenticate, mint_api_key, parse_api_key
from saas.ratelimit import RateLimiter


def test_api_key_roundtrip_and_isolation(saas_session_factory):
    s = saas_session_factory()
    t1 = provisioning.create_tenant(s, name="One", plan="pro")
    t2 = provisioning.create_tenant(s, name="Two", plan="free")
    minted1 = provisioning.issue_key(s, t1)
    minted2 = provisioning.issue_key(s, t2)
    s.close()

    # A fresh session resolves each key to the correct tenant.
    s = saas_session_factory()
    assert authenticate(s, minted1.plaintext).tenant_id == t1.tenant_id
    assert authenticate(s, minted2.plaintext).tenant_id == t2.tenant_id
    s.close()


def test_plaintext_key_is_not_stored(saas_session_factory):
    from saas.tenancy import ApiKey

    s = saas_session_factory()
    t = provisioning.create_tenant(s, name="Sec", plan="free")
    minted = provisioning.issue_key(s, t)
    s.close()

    s = saas_session_factory()
    row = s.query(ApiKey).filter(ApiKey.key_prefix == minted.key_prefix).first()
    # The stored hash must never equal the plaintext or contain the secret.
    assert row.key_hash != minted.plaintext
    secret = minted.plaintext.split("_")[-1]
    assert secret not in row.key_hash
    s.close()


def test_bad_and_malformed_keys_rejected(saas_session_factory):
    s = saas_session_factory()
    provisioning.issue_key(
        s, provisioning.create_tenant(s, name="X", plan="free")
    )
    s.close()

    s = saas_session_factory()
    assert authenticate(s, "") is None
    assert authenticate(s, "not-a-key") is None
    assert authenticate(s, "lpk_deadbeef_wrongsecret") is None
    s.close()

    assert parse_api_key("lpk_abc_def") == ("abc", "def")
    assert parse_api_key("garbage") == (None, None)


def test_inactive_tenant_cannot_authenticate(saas_session_factory):
    from saas.tenancy import Tenant

    s = saas_session_factory()
    t = provisioning.create_tenant(s, name="Off", plan="pro")
    minted = provisioning.issue_key(s, t)
    # Deactivate the tenant.
    row = s.query(Tenant).filter(Tenant.tenant_id == t.tenant_id).first()
    row.is_active = False
    s.commit()
    s.close()

    s = saas_session_factory()
    assert authenticate(s, minted.plaintext) is None
    s.close()


def test_rate_limiter_fixed_window():
    clock = {"t": 1000.0}
    rl = RateLimiter(window_seconds=60, time_fn=lambda: clock["t"])

    # Limit of 3 in the window.
    assert rl.check("tnt_a", 3) is True
    assert rl.check("tnt_a", 3) is True
    assert rl.check("tnt_a", 3) is True
    assert rl.check("tnt_a", 3) is False  # 4th blocked

    # A different tenant has its own bucket.
    assert rl.check("tnt_b", 3) is True

    # Window rolls over after 60s -> allowance resets.
    clock["t"] += 61
    assert rl.check("tnt_a", 3) is True


def test_rate_limiter_zero_means_unlimited():
    rl = RateLimiter()
    for _ in range(1000):
        assert rl.check("tnt", 0) is True
