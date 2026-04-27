# database/migrate.py
# Lightweight migration helpers for the local SQLite development database.
#
# Production deployments should use a proper migration tool such as Alembic.

import os
import sys

from sqlalchemy import inspect, text

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import get_engine
from database.schema import Base


NICHE_MARKET_COLUMNS = {
    "sub_sub_sub_industry": "VARCHAR(255) DEFAULT ''",
    "sub_sub_sub_sub_industry": "VARCHAR(255) DEFAULT ''",
    "ownership_sector": "VARCHAR(100)",
    "sector_code": "VARCHAR(50)",
    "sub_industry_code": "VARCHAR(50)",
    "sub_sub_industry_code": "VARCHAR(50)",
    "sub_sub_sub_industry_code": "VARCHAR(50)",
    "sub_sub_sub_sub_industry_code": "VARCHAR(50)",
    "primary_buyer_role": "VARCHAR(255)",
    "likely_compliance_regimes": "TEXT",
    "conditional_compliance_regimes": "TEXT",
    "compliance_tag_confidence": "VARCHAR(50)",
    "compliance_tag_basis": "TEXT",
    "recommended_cyber_themes": "TEXT",
    "regulatory_or_compliance_drivers": "TEXT",
    "source_notes": "TEXT",
    "source_status": "VARCHAR(50) DEFAULT 'seed'",
}

VENDOR_MATCH_COLUMNS = {
    "confidence_label": "VARCHAR(50)",
    "match_type": "VARCHAR(50)",
    "matched_terms": "TEXT",
    "is_fallback": "BOOLEAN DEFAULT 0",
}


DROP_INDEX_STATEMENTS = [
    "DROP INDEX IF EXISTS uq_niche_market_identity",
]


INDEX_STATEMENTS = [
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_niche_name_geography "
    "ON niche_markets (niche_name, geography)",
    "CREATE INDEX IF NOT EXISTS ix_niche_priority_score ON niche_markets (priority_score)",
    "CREATE INDEX IF NOT EXISTS ix_niche_priority_tier ON niche_markets (priority_tier)",
    "CREATE INDEX IF NOT EXISTS ix_niche_naics_code ON niche_markets (naics_code)",
    "CREATE INDEX IF NOT EXISTS ix_pain_point_niche_market_id ON pain_points (niche_market_id)",
    "CREATE INDEX IF NOT EXISTS ix_pain_point_category ON pain_points (cyber_category, cyber_subcategory)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_vendor_name ON vendors (vendor_name)",
    "CREATE INDEX IF NOT EXISTS ix_vendor_category ON vendors (cyber_category, cyber_subcategory)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_vendor_pain_point_match "
    "ON vendor_pain_point_map (vendor_id, pain_point_id)",
    "CREATE INDEX IF NOT EXISTS ix_vendor_match_pain_point "
    "ON vendor_pain_point_map (pain_point_id, match_score)",
    "CREATE INDEX IF NOT EXISTS ix_vendor_match_vendor ON vendor_pain_point_map (vendor_id)",
]


def _add_missing_columns(engine, table_name: str, column_definitions: dict) -> None:
    inspector = inspect(engine)
    existing_columns = {
        column["name"]
        for column in inspector.get_columns(table_name)
    }

    with engine.begin() as conn:
        for column_name, column_type in column_definitions.items():
            if column_name not in existing_columns:
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))


def _create_indexes(engine) -> None:
    with engine.begin() as conn:
        for statement in DROP_INDEX_STATEMENTS:
            conn.execute(text(statement))
        for statement in INDEX_STATEMENTS:
            conn.execute(text(statement))


def migrate() -> None:
    """Applies safe additive migrations for the current schema."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    _add_missing_columns(engine, "niche_markets", NICHE_MARKET_COLUMNS)
    _add_missing_columns(engine, "vendor_pain_point_map", VENDOR_MATCH_COLUMNS)
    _create_indexes(engine)
    print("Database migration completed.")


if __name__ == "__main__":
    migrate()
