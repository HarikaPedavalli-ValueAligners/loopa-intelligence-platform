# saas/entitlements.py
# Entitlement gating: maps a tenant's plan to allow/deny decisions on features
# and clamps requested quotas. Pure logic over saas.plans, no I/O.

from dataclasses import dataclass

from saas.plans import Feature, Plan, get_plan
from saas.tenancy import Tenant


class EntitlementError(Exception):
    """Raised when a tenant attempts to use a feature their plan does not grant."""

    def __init__(self, feature: str, plan_name: str):
        self.feature = feature
        self.plan_name = plan_name
        super().__init__(
            f"Plan '{plan_name}' does not include feature '{feature}'. "
            f"Upgrade required."
        )


@dataclass(frozen=True)
class Entitlements:
    """A resolved view of what a given tenant may do, derived from its plan."""

    plan: Plan

    @classmethod
    def for_tenant(cls, tenant: Tenant) -> "Entitlements":
        return cls(plan=get_plan(tenant.plan))

    def allows(self, feature: str) -> bool:
        return self.plan.has_feature(feature)

    def require(self, feature: str) -> None:
        """Raises EntitlementError unless the plan grants the feature."""
        if not self.allows(feature):
            raise EntitlementError(feature, self.plan.name)

    def clamp_page_size(self, requested: int) -> int:
        """Clamps a requested page size to the plan's per-request ceiling."""
        return self.plan.clamp_limit(requested)

    @property
    def max_niches_total(self) -> int:
        return self.plan.max_niches_total

    @property
    def rate_per_min(self) -> int:
        return self.plan.rate_per_min
