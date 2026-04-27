# agents/niche_market_importer.py
# Imports the 700+ niche market list from CSV or Excel into niche_markets.

import argparse
import os
import sys

import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import get_database_stats, upsert_niche_market_seed


COLUMN_ALIASES = {
    "industry": ["industry", "sector", "parent industry", "parent_industry"],
    "sub_industry": ["sub industry", "sub_industry", "sub-sector", "subsector"],
    "sub_sub_industry": [
        "sub sub industry",
        "sub_sub_industry",
        "niche",
        "niche market",
        "niche_market",
        "sub-sub-industry",
    ],
    "niche_name": ["niche name", "niche_name", "market name", "market_name"],
    "naics_code": ["naics", "naics code", "naics_code"],
    "geography": ["geography", "country", "region", "market"],
    "source_notes": ["notes", "source notes", "source_notes", "description"],
}


def _normalize_header(value: str) -> str:
    return str(value or "").strip().lower().replace("-", " ").replace("_", " ")


def _clean_value(value) -> str:
    if pd.isna(value) or value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _header_map(columns) -> dict:
    normalized = {_normalize_header(column): column for column in columns}
    mapping = {}

    for target, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            column = normalized.get(_normalize_header(alias))
            if column is not None:
                mapping[target] = column
                break

    return mapping


def read_niche_file(path: str, sheet_name: str = None) -> list:
    """Reads a CSV/XLSX file and returns normalized niche seed dicts."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    ext = os.path.splitext(path)[1].lower()
    if ext in {".xlsx", ".xls"}:
        df = pd.read_excel(path, sheet_name=sheet_name or 0)
    elif ext == ".csv":
        df = pd.read_csv(path)
    else:
        raise ValueError("Niche market importer supports .csv, .xlsx, and .xls files.")

    mapping = _header_map(df.columns)
    if "industry" not in mapping:
        raise ValueError("Input file must include an industry/sector column.")

    records = []
    for _, row in df.iterrows():
        record = {
            field: _clean_value(row.get(column))
            for field, column in mapping.items()
        }

        if not record.get("industry"):
            continue

        record.setdefault("sub_industry", "")
        record.setdefault("sub_sub_industry", "")
        record.setdefault("geography", "US")
        record["geography"] = record.get("geography") or "US"
        record["source_status"] = "seed"

        if not record.get("niche_name"):
            record["niche_name"] = " > ".join(
                p for p in [
                    record.get("industry"),
                    record.get("sub_industry"),
                    record.get("sub_sub_industry"),
                ] if p
            )

        records.append(record)

    return records


def import_niche_markets(path: str, sheet_name: str = None) -> dict:
    """Imports niche market seed rows and returns a summary."""
    records = read_niche_file(path, sheet_name=sheet_name)
    imported = 0
    errors = []

    for index, record in enumerate(records, start=1):
        try:
            upsert_niche_market_seed(record)
            imported += 1
        except Exception as exc:
            errors.append({"row": index, "error": str(exc), "record": record})

    return {
        "source": path,
        "total_rows": len(records),
        "imported": imported,
        "failed": len(errors),
        "errors": errors,
    }


def display_summary(summary: dict) -> None:
    print("\nLoopa Intelligence - Niche Market Importer")
    print("=" * 60)
    print(f"Source     : {summary['source']}")
    print(f"Rows       : {summary['total_rows']}")
    print(f"Imported   : {summary['imported']}")
    print(f"Failed     : {summary['failed']}")

    if summary["errors"]:
        print("\nErrors:")
        for error in summary["errors"][:10]:
            print(f"  Row {error['row']}: {error['error']}")

    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import niche market seed list from CSV or Excel.")
    parser.add_argument("path", help="Path to the niche market CSV/XLSX file")
    parser.add_argument("--sheet-name", help="Excel sheet name, defaults to first sheet")
    args = parser.parse_args()

    result = import_niche_markets(args.path, sheet_name=args.sheet_name)
    display_summary(result)
    print()
    get_database_stats()
