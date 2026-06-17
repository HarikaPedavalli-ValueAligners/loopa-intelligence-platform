# saas/config.py
# Centralized configuration for the Loopa SaaS wrapper.
#
# Everything is environment/flag driven and defaults to a SAFE state:
#   - The SaaS surface is OFF unless LOOPA_SAAS_ENABLED == "true".
#   - New tenants default to the free plan.
#   - Admin operations are disabled unless an admin token is configured.
#
# No secrets are hard-coded here. Reads from process env (optionally loaded
# from a .env file via python-dotenv when available).

import os
from dataclasses import dataclass

try:
    # Optional: load .env if python-dotenv is installed. Never required.
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional
    pass


def _as_bool(value, default=False):
    """Parses a permissive truthy string into a bool."""
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value, default=None):
    """Parses an int, returning default on empty/invalid input."""
    if value is None or str(value).strip() == "":
        return default
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class SaaSConfig:
    """Immutable snapshot of the SaaS wrapper configuration."""

    enabled: bool
    admin_token: str
    default_plan: str
    free_rate_per_min: int  # 0 means "use the plan default"

    @property
    def admin_enabled(self) -> bool:
        """Admin endpoints require BOTH the master flag and an admin token."""
        return self.enabled and bool(self.admin_token)


def load_config(env=None) -> SaaSConfig:
    """
    Builds a SaaSConfig from the given mapping (defaults to os.environ).

    Passing an explicit mapping makes this trivially testable without touching
    real process environment or any secret files.
    """
    env = os.environ if env is None else env

    return SaaSConfig(
        enabled=_as_bool(env.get("LOOPA_SAAS_ENABLED"), default=False),
        admin_token=(env.get("LOOPA_SAAS_ADMIN_TOKEN") or "").strip(),
        default_plan=(env.get("LOOPA_SAAS_DEFAULT_PLAN") or "free").strip().lower(),
        free_rate_per_min=_as_int(env.get("LOOPA_SAAS_FREE_RATE_PER_MIN"), default=0) or 0,
    )
