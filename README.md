# Loopa Intelligence Platform

AI-powered market intelligence for ranking cybersecurity niche markets, identifying pain points, matching vendors, and generating sales intelligence reports.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `.env` with local credentials. Do not commit `.env`.

For local development, keep:

```bash
ENVIRONMENT=development
SQLITE_DB_PATH=loopa_intelligence.db
```

For Azure SQL production, set:

```bash
ENVIRONMENT=production
AZURE_SQL_SERVER=...
AZURE_SQL_DATABASE=...
AZURE_SQL_USERNAME=...
AZURE_SQL_PASSWORD=...
AZURE_SQL_DRIVER=ODBC Driver 18 for SQL Server
AZURE_SQL_ENCRYPT=yes
AZURE_SQL_TRUST_SERVER_CERTIFICATE=no
```

For production AI, use Vertex AI once the GCP project ID, region, billing,
and ADC/service-account access are confirmed. Keep Developer API keys for
local experiments only.

```bash
AI_PROVIDER=vertex
AI_ENABLE_FALLBACK=true
OPENAI_API_KEY=...
OPENAI_MODEL=...
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3-pro-preview
GEMINI_THINKING_BUDGET=
VERTEX_API_KEY=...
VERTEX_MODEL=gemini-3-pro-preview
VERTEX_THINKING_BUDGET=
GOOGLE_CLOUD_PROJECT=...
GOOGLE_CLOUD_LOCATION=us-central1
GROQ_API_KEY=...
GROQ_MODEL=llama-3.3-70b-versatile
```

Supported primary providers are `openai`, `gemini`, `vertex`, and `groq`.
For deep research runs, use `gemini-3-pro-preview`; Gemini 3 Pro keeps thinking enabled by default, and optional thinking budget variables can be used if cost/latency tuning is needed.

## Current Operational Snapshot

As of the latest local/Azure sync:

- Niche market seeds: 1,032.
- Researched niches with generated pain points: 77.
- Pain points: 231.
- Vendors: 3,431.
- Valid vendor matches: 529.
- Latest batch run: run 11, `completed_with_errors`, 29 successes, 1 failure, stopped by provider quota.
- Azure SQL is reachable from the allowed network and has been synced with the cleaned local dataset.
- Production AI is paused pending Vertex project ID, region, billing/credits confirmation, and ADC/service-account access.

## Data Files

The vendor Excel files are intentionally ignored by git. Place them in `data/` before running the importer:

- `data/Vendor Database.xlsx`
- `data/Vendor Dataset for Clustering.xlsx`

Generated JSON reports and the local SQLite database are also ignored.

## Common Commands

```bash
python database/schema.py
python database/migrate.py
python agents/niche_market_importer.py data/niche_markets.csv
python agents/vendor_importer.py
python agents/batch_processor.py --limit 20
python agents/vendor_matcher.py
python utils/report_generator.py
python utils/sales_exporter.py --limit 100 --min-tier 2
python utils/monitoring.py
python utils/recalculate_scores.py
python scripts/check_azure_sql.py
python scripts/migrate_sqlite_to_azure.py --dry-run
python scripts/migrate_sqlite_to_azure.py --prune-orphans --upsert --dialect pymssql
python scheduler.py --run-now
```

Start the weekly scheduler:

```bash
python scheduler.py
```

Batch options:

```bash
python agents/batch_processor.py --limit 50
python agents/batch_processor.py --resume
python agents/batch_processor.py --only-failed
python agents/batch_processor.py --seed-list --limit 5
```

The batch processor reads from `niche_markets` by default. Use the niche market importer to load the 700+ market list before running a full batch.

Vendor matching now saves confidence metadata and defaults to real matches only:

```bash
python agents/vendor_matcher.py --min-confidence weak
python agents/vendor_matcher.py --min-confidence medium
python agents/vendor_matcher.py --include-fallback
```

Start the local JSON API for dashboard integration:

```bash
python api/server.py --port 8787
```

Useful endpoints:

- `GET /health`
- `GET /dashboard/summary`
- `GET /niches/top?limit=20`
- `GET /runs`

Run history is stored in:

- `intelligence_runs`
- `run_items`

## Scoring Model

Loopa uses Hamid's two-layer scoring model:

- Demand Score: cybersecurity urgency and market opportunity.
- Outbound Feasibility Score: ability to reach and convert buyers.
- Priority Score = Demand Score x Outbound Score / 100.

Variables with negative business meaning are inverted before contribution:

- Lower `cybersecurity_readiness` increases Demand Score.
- Lower `procurement_friction` increases Outbound Score.

This keeps all final scores on a 0-100 scale while preserving the intended business meaning of negative-weight variables.

Run tests:

```bash
python -m unittest
```

## Deployment and Workflow

Deployment assets are included for the next integration phase:

- `Dockerfile` and `docker-compose.yml` for API containerization.
- `.github/workflows/ci.yml` for unit test and migration validation.
- `scripts/smoke_check.py` for API health/integration checks.
- `docs/deployment.md` for local, Docker, and production commands.
- `docs/opsera_workflow.md` for the first Opsera workflow draft.

Useful Make targets:

```bash
make test
make migrate
make api
make smoke
make downstream
make docker-build
```

While Groq quota is limited, deploy and run non-AI workflows first:

```bash
python scheduler.py --run-now --skip-batch
```
