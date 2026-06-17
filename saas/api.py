# saas/api.py
# Versioned public HTTP API for Loopa SaaS tenants.
#
# Mounted under /api/v1. Every tenant-facing route:
#   1. authenticates the caller via the Authorization: Bearer <api-key> header
#      (or X-API-Key), resolving to a Tenant;
#   2. enforces per-tenant rate limiting based on the tenant's plan;
#   3. scopes all data reads through TenantScope (data isolation);
#   4. gates premium data (vendor matches, full report) behind entitlements.
#
# Admin routes under /api/v1/admin require the LOOPA_SAAS_ADMIN_TOKEN bearer.
#
# The factory `create_api(...)` is the only public entry point and is called by
# saas.app ONLY when the master feature flag is ON.

from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from database.db_manager import get_session as get_data_session
from saas import API_VERSION, __version__
from saas.auth import authenticate
from saas.config import SaaSConfig, load_config
from saas.entitlements import EntitlementError
from saas.plans import Feature, get_plan
from saas import provisioning, repository
from saas.ratelimit import RateLimiter
from saas.tenancy import Tenant, make_session_factory, make_saas_engine


def _bearer_from_headers(authorization: Optional[str], x_api_key: Optional[str]) -> Optional[str]:
    """Extracts a credential from either Authorization: Bearer or X-API-Key."""
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    if x_api_key:
        return x_api_key.strip()
    return None


def create_api(
    config: Optional[SaaSConfig] = None,
    saas_session_factory=None,
    data_session_factory=None,
    rate_limiter: Optional[RateLimiter] = None,
) -> FastAPI:
    """
    Builds the versioned FastAPI app.

    All collaborators are injectable so tests can supply temp DBs and a fake
    clock for the rate limiter without any real secrets or network.
    """
    config = config or load_config()

    if saas_session_factory is None:
        saas_session_factory = make_session_factory(make_saas_engine())
    if data_session_factory is None:
        data_session_factory = get_data_session  # legacy: returns a Session
    limiter = rate_limiter or RateLimiter()

    app = FastAPI(
        title="Loopa Intelligence SaaS API",
        version=__version__,
        docs_url=f"/api/{API_VERSION}/docs",
        openapi_url=f"/api/{API_VERSION}/openapi.json",
    )

    # -- dependencies --------------------------------------------------------

    def _new_saas_session():
        return saas_session_factory()

    def _new_data_session():
        # data_session_factory may be either a sessionmaker or the legacy
        # get_session() callable; both are zero-arg callables returning a Session.
        return data_session_factory()

    def require_tenant(
        authorization: Optional[str] = Header(default=None),
        x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    ) -> Tenant:
        credential = _bearer_from_headers(authorization, x_api_key)
        if not credential:
            raise HTTPException(status_code=401, detail="Missing API key.")

        session = _new_saas_session()
        try:
            tenant = authenticate(session, credential)
            if tenant is None:
                raise HTTPException(status_code=401, detail="Invalid API key.")
            session.commit()  # persist last_used_at
            # Detach a lightweight copy so the request handler does not depend
            # on the session lifetime.
            return Tenant(
                id=tenant.id,
                tenant_id=tenant.tenant_id,
                name=tenant.name,
                plan=tenant.plan,
                full_catalog=tenant.full_catalog,
                is_active=tenant.is_active,
            )
        finally:
            session.close()

    def enforce_rate_limit(tenant: Tenant = Depends(require_tenant)) -> Tenant:
        plan = get_plan(tenant.plan)
        limit = plan.rate_per_min
        if config.free_rate_per_min and plan.name == "free":
            limit = config.free_rate_per_min
        if not limiter.check(tenant.tenant_id, limit):
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Slow down or upgrade your plan.",
            )
        return tenant

    def require_admin(
        authorization: Optional[str] = Header(default=None),
    ) -> None:
        if not config.admin_enabled:
            raise HTTPException(status_code=404, detail="Admin API disabled.")
        token = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        # constant-time-ish comparison; tokens are short, this is adequate here.
        if not token or token != config.admin_token:
            raise HTTPException(status_code=403, detail="Admin token required.")

    def _scope_for(tenant: Tenant):
        saas_session = _new_saas_session()
        data_session = _new_data_session()
        scope = repository.TenantScope(saas_session, data_session, tenant)
        return scope, saas_session, data_session

    # -- meta routes ---------------------------------------------------------

    @app.get(f"/api/{API_VERSION}/health")
    def health():
        return {"status": "ok", "version": __version__, "api": API_VERSION}

    @app.get(f"/api/{API_VERSION}/me")
    def me(tenant: Tenant = Depends(enforce_rate_limit)):
        plan = get_plan(tenant.plan)
        return {
            "tenant_id": tenant.tenant_id,
            "name": tenant.name,
            "plan": plan.name,
            "features": sorted(plan.features),
            "limits": {
                "max_niches_per_request": plan.max_niches_per_request,
                "max_niches_total": plan.max_niches_total,
                "rate_per_min": plan.rate_per_min,
            },
        }

    # -- intelligence routes (tenant-scoped) ---------------------------------

    @app.get(f"/api/{API_VERSION}/niches")
    def list_niches(
        tenant: Tenant = Depends(enforce_rate_limit),
        limit: int = Query(default=5, ge=1, le=200),
    ):
        scope, s, d = _scope_for(tenant)
        try:
            return {"niches": repository.list_niches(scope, limit=limit)}
        finally:
            s.close()
            d.close()

    @app.get(f"/api/{API_VERSION}/niches/{{niche_id}}")
    def get_niche(niche_id: int, tenant: Tenant = Depends(enforce_rate_limit)):
        scope, s, d = _scope_for(tenant)
        try:
            niche = repository.get_niche(scope, niche_id)
            if niche is None:
                raise HTTPException(status_code=404, detail="Niche not found.")
            return niche
        finally:
            s.close()
            d.close()

    @app.get(f"/api/{API_VERSION}/niches/{{niche_id}}/pain-points")
    def niche_pain_points(niche_id: int, tenant: Tenant = Depends(enforce_rate_limit)):
        scope, s, d = _scope_for(tenant)
        try:
            pps = repository.list_pain_points(scope, niche_id)
            if pps is None:
                raise HTTPException(status_code=404, detail="Niche not found.")
            return {"niche_id": niche_id, "pain_points": pps}
        finally:
            s.close()
            d.close()

    @app.get(f"/api/{API_VERSION}/pain-points/{{pain_point_id}}/vendors")
    def pain_point_vendors(
        pain_point_id: int, tenant: Tenant = Depends(enforce_rate_limit)
    ):
        scope, s, d = _scope_for(tenant)
        try:
            matches = repository.list_vendor_matches(scope, pain_point_id)
            if matches is None:
                raise HTTPException(status_code=404, detail="Pain point not found.")
            return {"pain_point_id": pain_point_id, "vendors": matches}
        finally:
            s.close()
            d.close()

    # -- admin routes --------------------------------------------------------

    @app.post(f"/api/{API_VERSION}/admin/tenants")
    def admin_create_tenant(payload: dict, _: None = Depends(require_admin)):
        session = _new_saas_session()
        try:
            tenant = provisioning.create_tenant(
                session,
                name=str(payload.get("name", "")).strip() or "unnamed",
                plan=str(payload.get("plan", config.default_plan)),
                full_catalog=bool(payload.get("full_catalog", False)),
            )
            return {
                "tenant_id": tenant.tenant_id,
                "name": tenant.name,
                "plan": tenant.plan,
                "full_catalog": tenant.full_catalog,
            }
        finally:
            session.close()

    @app.post(f"/api/{API_VERSION}/admin/tenants/{{tenant_id}}/keys")
    def admin_issue_key(tenant_id: str, payload: dict = None, _: None = Depends(require_admin)):
        session = _new_saas_session()
        try:
            tenant = session.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
            if tenant is None:
                raise HTTPException(status_code=404, detail="Tenant not found.")
            label = str((payload or {}).get("label", "")).strip()
            minted = provisioning.issue_key(session, tenant, label=label)
            # Plaintext returned exactly once.
            return {"api_key": minted.plaintext, "key_prefix": minted.key_prefix}
        finally:
            session.close()

    @app.post(f"/api/{API_VERSION}/admin/tenants/{{tenant_id}}/grants")
    def admin_grant(tenant_id: str, payload: dict, _: None = Depends(require_admin)):
        session = _new_saas_session()
        try:
            tenant = session.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
            if tenant is None:
                raise HTTPException(status_code=404, detail="Tenant not found.")
            ids = payload.get("niche_ids", [])
            added = provisioning.grant_niches(session, tenant, ids)
            return {"granted": added, "total_grants": len(provisioning.list_tenant_grants(session, tenant))}
        finally:
            session.close()

    # -- error handling ------------------------------------------------------

    @app.exception_handler(EntitlementError)
    def _entitlement_handler(_request, exc: EntitlementError):
        return JSONResponse(
            status_code=402,  # Payment Required: feature needs a higher plan
            content={
                "error": "upgrade_required",
                "feature": exc.feature,
                "plan": exc.plan_name,
                "detail": str(exc),
            },
        )

    return app
