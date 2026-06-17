# saas/__init__.py
# Loopa Intelligence SaaS wrapper.
#
# This package wraps the existing market-intelligence platform as a sellable,
# multi-tenant SaaS WITHOUT modifying the existing platform's behavior. The
# whole surface is gated behind the LOOPA_SAAS_ENABLED feature flag (default
# OFF), so importing this package has no effect on the legacy code paths.
#
# Layers:
#   config        - flag and environment loading
#   plans         - plan tiers, entitlements, and quotas
#   tenancy       - tenant identity + per-tenant data isolation
#   entitlements  - feature/quota gating helpers
#   ratelimit     - per-tenant request rate limiting
#   auth          - API key minting and verification (stdlib hashing only)
#   repository    - tenant-scoped queries over the existing intelligence data
#   api           - versioned public HTTP API
#   app           - composition root (returns the app only when the flag is ON)

__all__ = ["__version__", "API_VERSION"]

__version__ = "0.1.0"
API_VERSION = "v1"
