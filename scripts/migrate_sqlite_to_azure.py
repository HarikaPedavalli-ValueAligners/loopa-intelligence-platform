import argparse
import os
import sys
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import create_engine, select, text

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import PROJECT_ROOT, get_database_url
from database.schema import (
    AccountLead,
    Base,
    DataQualityFinding,
    DataQualityRun,
    IntelligenceRun,
    NicheMarket,
    NicheRadarScore,
    NicheRadarScoreHistory,
    NicheRadarVariable,
    PainPoint,
    RunItem,
    Vendor,
    VendorAlert,
    VendorIntelligenceProfile,
    VendorIntelligenceVariable,
    VendorPainPointMap,
    VendorScoreHistory,
)


TABLES = [
    NicheMarket.__table__,
    Vendor.__table__,
    IntelligenceRun.__table__,
    PainPoint.__table__,
    RunItem.__table__,
    VendorPainPointMap.__table__,
    VendorIntelligenceProfile.__table__,
    VendorIntelligenceVariable.__table__,
    VendorScoreHistory.__table__,
    VendorAlert.__table__,
    NicheRadarScore.__table__,
    NicheRadarVariable.__table__,
    NicheRadarScoreHistory.__table__,
    AccountLead.__table__,
    DataQualityRun.__table__,
    DataQualityFinding.__table__,
]

IDENTITY_TABLES = {
    "niche_markets",
    "vendors",
    "intelligence_runs",
    "pain_points",
    "run_items",
    "vendor_pain_point_map",
    "vendor_intelligence_profiles",
    "vendor_intelligence_variables",
    "vendor_score_history",
    "vendor_alerts",
    "niche_radar_scores",
    "niche_radar_variables",
    "niche_radar_score_history",
    "account_leads",
    "data_quality_runs",
    "data_quality_findings",
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


def selected_tables(table_names: str = None) -> list:
    if not table_names:
        return TABLES
    requested = {name.strip() for name in table_names.split(",") if name.strip()}
    known = {table.name: table for table in TABLES}
    unknown = sorted(requested - set(known))
    if unknown:
        raise ValueError(f"Unknown table names: {', '.join(unknown)}")
    return [table for table in TABLES if table.name in requested]


def count_source_rows(source_engine, tables: list = None) -> dict:
    tables = tables or TABLES
    counts = {}
    with source_engine.connect() as connection:
        for table in tables:
            counts[table.name] = len(connection.execute(select(table)).all())
        if any(table.name == "vendor_pain_point_map" for table in tables):
            valid_matches = connection.execute(text(
                """
                SELECT COUNT(*)
                FROM vendor_pain_point_map vppm
                JOIN vendors v ON v.id = vppm.vendor_id
                JOIN pain_points p ON p.id = vppm.pain_point_id
                """
            )).scalar()
            counts["vendor_pain_point_map_valid"] = valid_matches
            counts["vendor_pain_point_map_orphan"] = counts["vendor_pain_point_map"] - valid_matches
    return counts


def prune_orphan_vendor_matches(source_engine, dry_run: bool = False) -> int:
    orphan_count_sql = text(
        """
        SELECT COUNT(*)
        FROM vendor_pain_point_map vppm
        LEFT JOIN vendors v ON v.id = vppm.vendor_id
        LEFT JOIN pain_points p ON p.id = vppm.pain_point_id
        WHERE v.id IS NULL OR p.id IS NULL
        """
    )
    prune_sql = text(
        """
        DELETE FROM vendor_pain_point_map
        WHERE vendor_id NOT IN (SELECT id FROM vendors)
           OR pain_point_id NOT IN (SELECT id FROM pain_points)
        """
    )

    with source_engine.begin() as connection:
        orphan_count = connection.execute(orphan_count_sql).scalar()
        if orphan_count and not dry_run:
            connection.execute(prune_sql)
        return orphan_count


def source_id_sets(source) -> dict:
    return {
        "niche_markets": {row.id for row in source.execute(select(NicheMarket.__table__.c.id)).all()},
        "vendors": {row.id for row in source.execute(select(Vendor.__table__.c.id)).all()},
        "pain_points": {row.id for row in source.execute(select(PainPoint.__table__.c.id)).all()},
        "intelligence_runs": {row.id for row in source.execute(select(IntelligenceRun.__table__.c.id)).all()},
        "vendor_intelligence_profiles": {
            row.id for row in source.execute(select(VendorIntelligenceProfile.__table__.c.id)).all()
        },
        "niche_radar_scores": {
            row.id for row in source.execute(select(NicheRadarScore.__table__.c.id)).all()
        },
        "data_quality_runs": {
            row.id for row in source.execute(select(DataQualityRun.__table__.c.id)).all()
        },
    }


def target_id_set(target, table) -> set:
    return {row.id for row in target.execute(select(table.c.id)).all()}


def target_vendor_match_keys(target) -> set:
    return {
        (row.vendor_id, row.pain_point_id)
        for row in target.execute(
            select(
                VendorPainPointMap.__table__.c.vendor_id,
                VendorPainPointMap.__table__.c.pain_point_id,
            )
        ).all()
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
    if table_name == "vendor_intelligence_profiles":
        return [row for row in rows if row.get("vendor_id") in ids["vendors"]]
    if table_name in {"vendor_intelligence_variables", "vendor_score_history", "vendor_alerts"}:
        return [
            row for row in rows
            if row.get("profile_id") in ids["vendor_intelligence_profiles"]
        ]
    if table_name == "niche_radar_scores":
        return [row for row in rows if row.get("niche_market_id") in ids["niche_markets"]]
    if table_name in {"niche_radar_variables", "niche_radar_score_history"}:
        return [
            row for row in rows
            if row.get("score_id") in ids["niche_radar_scores"]
        ]
    if table_name == "account_leads":
        return [
            row for row in rows
            if row.get("niche_market_id") is None
            or row.get("niche_market_id") in ids["niche_markets"]
        ]
    if table_name == "data_quality_findings":
        return [row for row in rows if row.get("run_id") in ids["data_quality_runs"]]
    return rows


def migrate(
    source_path: str,
    replace: bool = False,
    dry_run: bool = False,
    dialect: str = "pyodbc",
    recreate: bool = False,
    upsert: bool = False,
    prune_orphans: bool = False,
    table_names: str = None,
) -> dict:
    tables = selected_tables(table_names)
    source_engine = create_engine(sqlite_url(source_path))
    pruned_count = 0
    if prune_orphans:
        pruned_count = prune_orphan_vendor_matches(source_engine, dry_run=dry_run)
    counts = count_source_rows(source_engine, tables)
    if prune_orphans:
        counts["vendor_pain_point_map_would_prune" if dry_run else "vendor_pain_point_map_pruned"] = pruned_count

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
            for table in reversed(tables):
                target.execute(table.delete())

        for table in tables:
            rows = [dict(row._mapping) for row in source.execute(select(table)).all()]
            original_count = len(rows)
            rows = filter_rows(table.name, rows, ids)
            skipped_count = original_count - len(rows)
            if skipped_count:
                print(f"Skipping {skipped_count} orphan rows from {table.name}")

            if upsert:
                existing_ids = target_id_set(target, table)
                insert_rows = []
                update_rows = []
                natural_key_updates = []

                existing_vendor_match_keys = (
                    target_vendor_match_keys(target)
                    if table.name == "vendor_pain_point_map"
                    else set()
                )

                for row in rows:
                    if row.get("id") in existing_ids:
                        update_rows.append(row)
                    elif table.name == "vendor_pain_point_map" and (
                        row.get("vendor_id"),
                        row.get("pain_point_id"),
                    ) in existing_vendor_match_keys:
                        natural_key_updates.append(row)
                    else:
                        insert_rows.append(row)

                for row in update_rows:
                    row_id = row["id"]
                    values = {key: value for key, value in row.items() if key != "id"}
                    if values:
                        target.execute(
                            table.update()
                            .where(table.c.id == row_id)
                            .values(**values)
                        )

                for row in natural_key_updates:
                    values = {key: value for key, value in row.items() if key != "id"}
                    if values:
                        target.execute(
                            table.update()
                            .where(table.c.vendor_id == row["vendor_id"])
                            .where(table.c.pain_point_id == row["pain_point_id"])
                            .values(**values)
                        )

                if insert_rows:
                    identity_insert = target.dialect.name == "mssql" and table.name in IDENTITY_TABLES
                    if identity_insert:
                        target.execute(text(f"SET IDENTITY_INSERT {table.name} ON"))
                    target.execute(table.insert(), insert_rows)
                    if identity_insert:
                        target.execute(text(f"SET IDENTITY_INSERT {table.name} OFF"))

                inserted_counts[table.name] = len(insert_rows)
                natural = f", natural-key updated {len(natural_key_updates)}" if natural_key_updates else ""
                print(f"{table.name}: updated {len(update_rows)}{natural}, inserted {len(insert_rows)}")
                continue

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
        "--upsert",
        action="store_true",
        help="Update rows that already exist in Azure and insert rows missing by primary key",
    )
    parser.add_argument(
        "--prune-orphans",
        action="store_true",
        help="Delete local vendor matches that reference missing vendors or pain points before migrating",
    )
    parser.add_argument(
        "--dialect",
        choices=["pyodbc", "pymssql"],
        default="pyodbc",
        help="Use pyodbc for production parity or pymssql for local diagnostics.",
    )
    parser.add_argument(
        "--tables",
        help="Comma-separated subset of tables to migrate, e.g. account_leads,data_quality_runs,data_quality_findings",
    )
    args = parser.parse_args()

    counts = migrate(
        args.source,
        replace=args.replace,
        dry_run=args.dry_run,
        dialect=args.dialect,
        recreate=args.recreate,
        upsert=args.upsert,
        prune_orphans=args.prune_orphans,
        table_names=args.tables,
    )
    print("SQLite to Azure migration plan" if args.dry_run else "SQLite to Azure migration complete")
    for table_name, count in counts.items():
        print(f"{table_name}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
