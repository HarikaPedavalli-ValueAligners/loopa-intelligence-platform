import argparse
import os
import sys
from pathlib import Path

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


def count_source_rows(source_engine) -> dict:
    counts = {}
    with source_engine.connect() as connection:
        for table in TABLES:
            counts[table.name] = len(connection.execute(select(table)).all())
    return counts


def migrate(source_path: str, replace: bool = False, dry_run: bool = False) -> dict:
    source_engine = create_engine(sqlite_url(source_path))
    counts = count_source_rows(source_engine)

    if dry_run:
        return counts

    os.environ["ENVIRONMENT"] = "production"
    target_engine = create_engine(get_database_url(), pool_pre_ping=True)
    Base.metadata.create_all(target_engine)

    with source_engine.connect() as source, target_engine.begin() as target:
        if replace:
            for table in reversed(TABLES):
                target.execute(table.delete())

        for table in TABLES:
            rows = [dict(row._mapping) for row in source.execute(select(table)).all()]
            if rows:
                identity_insert = target.dialect.name == "mssql" and table.name in IDENTITY_TABLES
                if identity_insert:
                    target.execute(text(f"SET IDENTITY_INSERT {table.name} ON"))
                target.execute(table.insert(), rows)
                if identity_insert:
                    target.execute(text(f"SET IDENTITY_INSERT {table.name} OFF"))

    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy local SQLite Loopa data into Azure SQL.")
    parser.add_argument("--source", default=os.getenv("SQLITE_DB_PATH", "loopa_intelligence.db"))
    parser.add_argument("--replace", action="store_true", help="Delete target table data before insert")
    parser.add_argument("--dry-run", action="store_true", help="Only count local source rows")
    args = parser.parse_args()

    counts = migrate(args.source, replace=args.replace, dry_run=args.dry_run)
    print("SQLite to Azure migration plan" if args.dry_run else "SQLite to Azure migration complete")
    for table_name, count in counts.items():
        print(f"{table_name}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
