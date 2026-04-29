# Loopa Deployment Guide

This guide covers the deployable pieces that can move forward even when AI batch processing is waiting on Vertex production access.

## Runtime Components

- `api/server.py`: JSON API for dashboards and integration checks.
- `scheduler.py`: weekly workflow runner.
- `agents/batch_processor.py`: AI enrichment runner. This should be quota-gated in production.
- `agents/vendor_matcher.py`, `utils/sales_exporter.py`, `utils/monitoring.py`: downstream non-AI workflow.

## Local Deployment

```bash
cp .env.example .env
make setup
make test
make migrate
make api
```

In another terminal:

```bash
make smoke
```

## Docker Deployment

```bash
docker compose up --build loopa-api
```

The API listens on:

```text
http://127.0.0.1:8787
```

Health endpoint:

```text
GET /health
```

## Production Environment

Use environment variables instead of committed config:

```text
ENVIRONMENT=production
DATABASE_URL=<preferred full SQLAlchemy URL>
AI_PROVIDER=vertex
AI_ENABLE_FALLBACK=true
OPENAI_API_KEY=<secret>
OPENAI_MODEL=<model approved for production batch research>
GEMINI_API_KEY=<secret>
GEMINI_MODEL=gemini-3-pro-preview
GEMINI_THINKING_BUDGET=
VERTEX_API_KEY=<optional Vertex express key for local diagnostics>
VERTEX_MODEL=gemini-3-pro-preview
VERTEX_THINKING_BUDGET=
GOOGLE_CLOUD_PROJECT=<GCP project ID, not project number>
GOOGLE_CLOUD_LOCATION=us-central1
GROQ_API_KEY=<secret>
GROQ_MODEL=llama-3.3-70b-versatile
```

Supported `AI_PROVIDER` values:

- `vertex`: production path using GCP project/location credentials, ADC, service account, or Workload Identity.
- `gemini`: local/dev path with a Gemini Developer API key. Do not use this path for the 1,000+ niche production run.
- `openai`: OpenAI path.
- `groq`: fallback path.

If `DATABASE_URL` is not set, Azure SQL variables are used:

```text
AZURE_SQL_SERVER=
AZURE_SQL_DATABASE=
AZURE_SQL_USERNAME=
AZURE_SQL_PASSWORD=
AZURE_SQL_PORT=1433
AZURE_SQL_DRIVER=ODBC Driver 18 for SQL Server
AZURE_SQL_ENCRYPT=yes
AZURE_SQL_TRUST_SERVER_CERTIFICATE=no
```

## Recommended Production Commands

API:

```bash
python api/server.py --host 0.0.0.0 --port 8787
```

Non-AI downstream refresh:

```bash
python scheduler.py --run-now --skip-batch
```

Quota-gated AI batch after Vertex access is validated:

```bash
python agents/batch_processor.py --resume --limit 20 --delay 1 --ai-retries 1
```

Start with one item, then 20, then 50. Only continue after quality, cost, quota, and runtime stability are confirmed.

## Azure SQL Preflight

After the SQL firewall allows the current client IP and secrets are loaded into `.env`:

```bash
python scripts/check_azure_sql.py
```

If local macOS ODBC Driver 18 is unavailable, use the diagnostic fallback:

```bash
python scripts/check_azure_sql.py --dialect pymssql
```

Dry-run local row counts before migration:

```bash
python scripts/migrate_sqlite_to_azure.py --dry-run --prune-orphans
```

Initial Azure load:

```bash
python scripts/migrate_sqlite_to_azure.py
```

Incremental Azure sync after local runs:

```bash
python scripts/migrate_sqlite_to_azure.py --prune-orphans --upsert --dialect pymssql
```

Use `--replace` only when intentionally rebuilding the Azure database from the local SQLite copy.
Use `--recreate` only for a first-time empty production database or a deliberate rebuild.
