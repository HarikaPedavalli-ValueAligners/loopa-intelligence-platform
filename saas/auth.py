# saas/auth.py
# API key minting and verification for tenant authentication.
#
# Uses ONLY the Python standard library (secrets, hmac, hashlib) so there is no
# extra dependency and nothing secret is bundled. Keys are stored as a salted
# HMAC-SHA256 hash; the plaintext is shown exactly once at mint time.
#
# Key format (plaintext, returned once): "lpk_<prefix>_<secret>"
#   - lpk_       : fixed, human-recognizable namespace ("loopa key")
#   - <prefix>   : public lookup handle, stored in cleartext (NOT secret)
#   - <secret>   : high-entropy secret, only its HMAC hash is stored
#
# The verification flow:
#   1. Parse the prefix from the presented key (cheap, no DB hashing yet).
#   2. Look up the ApiKey row by prefix.
#   3. HMAC-hash the presented secret with the row's-independent server salt and
#      compare in constant time against the stored hash.

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from saas.tenancy import ApiKey, Tenant


KEY_NAMESPACE = "lpk"


def _server_salt() -> bytes:
    """
    Returns the salt used to HMAC API-key secrets.

    Prefers LOOPA_SAAS_ADMIN_TOKEN so that hashes are tied to the deployment's
    own secret (rotating the admin token invalidates outstanding keys, which is
    a safe failure mode). Falls back to a fixed, non-secret label only so that
    tests run without any configured secret; in that mode keys are still opaque
    and constant-time-compared, they are simply not deployment-bound.
    """
    token = (os.environ.get("LOOPA_SAAS_ADMIN_TOKEN") or "").strip()
    if token:
        return token.encode("utf-8")
    return b"loopa-saas-local-dev-salt"


def hash_secret(secret: str) -> str:
    """Returns the hex HMAC-SHA256 of a key secret under the server salt."""
    return hmac.new(_server_salt(), secret.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class MintedKey:
    """Result of minting a key. `plaintext` is shown to the caller exactly once."""

    plaintext: str
    key_prefix: str


def mint_api_key(session, tenant: Tenant, label: str = "") -> MintedKey:
    """
    Creates a new API key for a tenant, persists only its hash, and returns the
    plaintext once. The caller is responsible for committing the session.
    """
    prefix = secrets.token_hex(6)        # 12 hex chars, public
    secret = secrets.token_urlsafe(24)   # high-entropy secret part
    plaintext = f"{KEY_NAMESPACE}_{prefix}_{secret}"

    row = ApiKey(
        tenant_pk=tenant.id,
        key_prefix=prefix,
        key_hash=hash_secret(secret),
        label=label or "",
        is_active=True,
    )
    session.add(row)
    return MintedKey(plaintext=plaintext, key_prefix=prefix)


def parse_api_key(presented: str):
    """
    Splits a presented plaintext key into (prefix, secret).

    Returns (None, None) for anything that does not match the expected shape, so
    malformed input is rejected cheaply before any DB or crypto work.
    """
    if not presented or not isinstance(presented, str):
        return None, None
    # Split on the FIRST two underscores only. The namespace and prefix never
    # contain '_', but the urlsafe secret can, so the remainder is the secret.
    parts = presented.strip().split("_", 2)
    if len(parts) != 3 or parts[0] != KEY_NAMESPACE:
        return None, None
    prefix, secret = parts[1], parts[2]
    if not prefix or not secret:
        return None, None
    return prefix, secret


def authenticate(session, presented_key: str) -> Optional[Tenant]:
    """
    Resolves a presented API key to its active Tenant, or None if the key is
    missing, malformed, unknown, inactive, or belongs to an inactive tenant.

    Performs a constant-time comparison on the secret hash.
    """
    prefix, secret = parse_api_key(presented_key)
    if not prefix or not secret:
        return None

    row = (
        session.query(ApiKey)
        .filter(ApiKey.key_prefix == prefix, ApiKey.is_active.is_(True))
        .first()
    )
    if row is None:
        return None

    expected = row.key_hash
    candidate = hash_secret(secret)
    if not hmac.compare_digest(expected, candidate):
        return None

    tenant = session.query(Tenant).filter(Tenant.id == row.tenant_pk).first()
    if tenant is None or not tenant.is_active:
        return None

    row.last_used_at = datetime.now()
    return tenant
