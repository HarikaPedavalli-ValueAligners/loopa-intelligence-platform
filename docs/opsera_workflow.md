# Opsera Workflow Draft

Use this as the first implementation outline for Hamid's Opsera integration request.

## Workflow 1: CI Validation

Trigger: push or pull request.

Steps:

1. Checkout repository.
2. Install Python 3.11.
3. Install `unixodbc-dev` and Microsoft ODBC Driver 18.
4. Install `requirements.txt`.
5. Run `python -m unittest`.
6. Run `python database/migrate.py`.

Success criteria:

- All unit tests pass.
- Migrations run without import or schema errors.

## Workflow 2: API Deployment

Trigger: manual or merge to main.

Steps:

1. Build Docker image from `Dockerfile`.
2. Inject runtime secrets from Opsera secret store.
3. Start API container with `python api/server.py --host 0.0.0.0 --port 8787`.
4. Run smoke check against `/health`, `/dashboard/summary`, `/niches/top`, and `/runs`.

Success criteria:

- Container healthcheck passes.
- `scripts/smoke_check.py` exits successfully.

## Workflow 3: Downstream Refresh

Trigger: schedule or manual.

Command:

```bash
python scheduler.py --run-now --skip-batch
```

Purpose:

- Re-run vendor matching.
- Rebuild sales export.
- Rebuild monitoring status.
- Avoid consuming AI quota.

## Workflow 4: Quota-Gated AI Batch

Trigger: manual approval only until provider quota is upgraded.

Command:

```bash
python agents/batch_processor.py --resume --limit 50 --delay 1 --ai-retries 1
```

Guardrails:

- Start with `--limit 20`.
- Increase to `--limit 50` only after a clean run.
- Keep default rate-limit stop behavior enabled.
- Do not use `--continue-on-rate-limit` in production.

## Parallel Project Notes

Opsera can run Workflow 1 and API deployment independently of the AI batch. The AI batch should be isolated because Groq quota is currently the limiting resource. Vendor matching and exports can run in parallel after any successful batch completion.
