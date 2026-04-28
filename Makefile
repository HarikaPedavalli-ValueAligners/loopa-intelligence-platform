.PHONY: setup test migrate api smoke downstream weekly azure-check azure-migrate-dry-run docker-build docker-up docker-down

setup:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

test:
	.venv/bin/python -m unittest

migrate:
	.venv/bin/python database/migrate.py

api:
	.venv/bin/python api/server.py --host 127.0.0.1 --port 8787

smoke:
	.venv/bin/python scripts/smoke_check.py

downstream:
	.venv/bin/python agents/vendor_matcher.py --min-confidence weak
	.venv/bin/python utils/sales_exporter.py --limit 100 --min-tier 2
	.venv/bin/python utils/monitoring.py

weekly:
	.venv/bin/python scheduler.py --run-now

azure-check:
	.venv/bin/python scripts/check_azure_sql.py

azure-migrate-dry-run:
	.venv/bin/python scripts/migrate_sqlite_to_azure.py --dry-run

docker-build:
	docker build -t loopa-intelligence-platform .

docker-up:
	docker compose up --build loopa-api

docker-down:
	docker compose down
