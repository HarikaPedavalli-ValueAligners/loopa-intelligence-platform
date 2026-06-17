# saas/app.py
# Composition root for the Loopa SaaS wrapper.
#
# This is the ONLY place that decides whether the SaaS surface exists at all.
# When LOOPA_SAAS_ENABLED is not exactly "true", build_app() returns a tiny
# "disabled" app (every route -> 404) so that deploying this code with the flag
# OFF leaves the existing platform behavior completely unchanged.
#
# Run locally (requires uvicorn, which is NOT a hard dependency of the repo):
#   LOOPA_SAAS_ENABLED=true python -m uvicorn saas.app:app --reload
#
# `app` is created at import time from the current environment. `build_app()`
# lets tests construct an app with an explicit config.

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from saas import API_VERSION, __version__
from saas.config import SaaSConfig, load_config


_LANDING_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Loopa Intelligence - Market Intelligence as a Service</title>
  <style>
    :root { color-scheme: light dark; }
    body { font-family: system-ui, sans-serif; margin: 0; padding: 0;
           background: #0b1020; color: #e8ecf4; }
    .wrap { max-width: 760px; margin: 0 auto; padding: 64px 24px; }
    h1 { font-size: 2.2rem; margin: 0 0 8px; }
    .tag { color: #8aa0c6; font-size: 1.1rem; margin-bottom: 32px; }
    .card { background: #131a2e; border: 1px solid #243150; border-radius: 12px;
            padding: 20px 24px; margin: 16px 0; }
    a { color: #7db4ff; }
    code { background: #0b1020; padding: 2px 6px; border-radius: 6px; }
    .tiers { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
    .tier h3 { margin: 0 0 6px; }
    .muted { color: #8aa0c6; font-size: 0.9rem; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Loopa Intelligence</h1>
    <div class="tag">Cybersecurity market intelligence, delivered as an API.</div>

    <div class="card">
      <strong>Get started</strong>
      <p class="muted">Authenticate every request with your API key:</p>
      <code>Authorization: Bearer lpk_&lt;your-key&gt;</code>
      <p class="muted">Then call the versioned API:</p>
      <code>GET /api/__API_VERSION__/niches</code><br/>
      <p class="muted">Explore the full reference at
        <a href="/api/__API_VERSION__/docs">/api/__API_VERSION__/docs</a>.</p>
    </div>

    <div class="tiers">
      <div class="card tier"><h3>Free</h3>
        <p class="muted">Top niches and pain points. Capped results.</p></div>
      <div class="card tier"><h3>Pro</h3>
        <p class="muted">Vendor matches and full reports. Higher limits.</p></div>
      <div class="card tier"><h3>Enterprise</h3>
        <p class="muted">Full catalog, exports, generous rate limits.</p></div>
    </div>

    <p class="muted">API version __API_VERSION__ &middot; build __VERSION__</p>
  </div>
</body>
</html>
"""


def _disabled_app() -> FastAPI:
    """A minimal app used when the SaaS flag is OFF: nothing is exposed."""
    app = FastAPI(
        title="Loopa Intelligence SaaS (disabled)",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/{_path:path}")
    def _gone(_path: str = ""):
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="SaaS surface is disabled.")

    return app


def build_app(config: SaaSConfig = None) -> FastAPI:
    """
    Returns the SaaS app for the given config.

    Flag OFF -> a 404-only app (existing platform behavior unchanged).
    Flag ON  -> the full versioned API plus a landing page.
    """
    config = config or load_config()

    if not config.enabled:
        return _disabled_app()

    # Import lazily so that the heavy API graph is only constructed when enabled.
    from saas.api import create_api

    app = create_api(config=config)

    landing = _LANDING_HTML.replace("__API_VERSION__", API_VERSION).replace(
        "__VERSION__", __version__
    )

    @app.get("/", response_class=HTMLResponse)
    def landing_page():
        return landing

    return app


# Module-level app for `uvicorn saas.app:app`. Built from current environment.
app = build_app()
