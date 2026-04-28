import argparse
import os
import sys
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import create_engine, select, text

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import PROJECT_ROOT, get_database_url
from database.schema import (
    Base,
    IntelligenceRun,
    NicheMarket,
    PainPoint,
    RunItem,
    Vendor,
    VendorPainPointMap,
)


TABLES = [
    NicheMarket.__table__,
    Vendor.__table__,
    IntelligenceRun.__table__,
    PainPoint.__table__,
    RunItem.__table__,
    VendorPainPointMap.__table__,
]

IDENTITY_TABLES = {
    "niche_markets",
    "vendors",
    "intelligence_runs",
    "pain_points",
    "run_items",
    "vendor_pain_point_map",
}


def sqlite_url(path: str) -> str:
    db_path = Path(path)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    return f"sqlite:///{db_path}"


def pymssql_database_url() -> str:
    server = os.getenv("AZURE_SQL_SERVER")
    database = os.getenv("AZURE_SQL_DATABASE")
    username = quote_plus(os.getenv("AZURE_SQL_USERNAME", ""))
    password = quote_plus(os.getenv("AZURE_SQL_PASSWORD", ""))
    return f"mssql+pymssql://{username}:{password}@{server}:1433/{database}"


def count_source_rows(source_engine) -> dict:
    counts = {}
    with source_engine.connect() as connection:
        for table in TABLES:
            counts[table.name] = len(connection.execute(select(table)).all())
    return counts


def source_id_sets(source) -> dict:
    return {
        "niche_markets": {row.id for row in source.execute(select(NicheMarket.__table__.c.id)).all()},
        "vendors": {row.id for row in source.execute(select(Vendor.__table__.c.id)).all()},
        "pain_points": {row.id for row in source.execute(select(PainPoint.__table__.c.id)).all()},
        "intelligence_runs": {row.id for row in source.execute(select(IntelligenceRun.__table__.c.id)).all()},
    }


def filter_rows(table_name: str, rows: list, ids: dict) -> list:
    if table_name == "pain_points":
        return [row for row in rows if row.get("niche_market_id") in ids["niche_markets"]]
    if table_name == "run_items":
        return [
            row for row in rows
            if row.get("run_id") in ids["intelligence_runs"]
            and row.get("niche_market_id") in ids["niche_markets"]
        ]
    if table_name == "vendor_pain_point_map":
        return [
            row for row in rows
            if row.get("vendor_id") in ids["vendors"]
            and row.get("pain_point_id") in ids["pain_points"]
        ]
    return rows


def migrate(
    source_path: str,
    replace: bool = False,
    dry_run: bool = False,
    dialect: str = "pyodbc",
    recreate: bool = False,
) -> dict:
    source_engine = create_engine(sqlite_url(source_path))
    counts = count_source_rows(source_engine)

    if dry_run:
        return counts

    os.environ["ENVIRONMENT"] = "production"
    database_url = pymssql_database_url() if dialect == "pymssql" else get_database_url()
    target_engine = create_engine(database_url, pool_pre_ping=True)
    if recreate:
        Base.metadata.drop_all(target_engine)
    Base.metadata.create_all(target_engine)

    with source_engine.connect() as source, target_engine.begin() as target:
        ids = source_id_sets(source)
        inserted_counts = {}
        if replace:
            for table in reversed(TABLES):
                target.execute(table.delete())

        for table in TABLES:
            rows = [dict(row._mapping) for row in source.execute(select(table)).all()]
            original_count = len(rows)
            rows = filter_rows(table.name, rows, ids)
            skipped_count = original_count - len(rows)
            if skipped_count:
                print(f"Skipping {skipped_count} orphan rows from {table.name}")
            if rows:
                identity_insert = target.dialect.name == "mssql" and table.name in IDENTITY_TABLES
                if identity_insert:
                    target.execute(text(f"SET IDENTITY_INSERT {table.name} ON"))
                target.execute(table.insert(), rows)
                if identity_insert:
                    target.execute(text(f"SET IDENTITY_INSERT {table.name} OFF"))
            inserted_counts[table.name] = len(rows)

    return inserted_counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy local SQLite Loopa data into Azure SQL.")
    parser.add_argument("--source", default=os.getenv("SQLITE_DB_PATH", "loopa_intelligence.db"))
    parser.add_argument("--replace", action="store_true", help="Delete target table data before insert")
    parser.add_argument("--recreate", action="store_true", help="Drop and recreate target tables before insert")
    parser.add_argument("--dry-run", action="store_true", help="Only count local source rows")
    parser.add_argument(
        "--dialect",
        choices=["pyodbc", "pymssql"],
        default="pyodbc",
        help="Use pyodbc for production parity or pymssql for local diagnostics.",
    )
    args = parser.parse_args()

    counts = migrate(
        args.source,
        replace=args.replace,
        dry_run=args.dry_run,
        dialect=args.dialect,
        recreate=args.recreate,
    )
    print("SQLite to Azure migration plan" if args.dry_run else "SQLite to Azure migration complete")
    for table_name, count in counts.items():
        print(f"{table_name}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
