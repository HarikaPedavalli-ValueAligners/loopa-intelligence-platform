# Loopa Deployment Guide

This guide covers the deployable pieces that can move forward even when AI batch processing is waiting on provider quota.

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
GROQ_API_KEY=<secret>
GROQ_MODEL=llama-3.3-70b-versatile
```

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

Quota-gated AI batch:

```bash
python agents/batch_processor.py --resume --limit 50 --delay 1 --ai-retries 1
```

Only run the AI batch when the provider account has enough daily token capacity.
