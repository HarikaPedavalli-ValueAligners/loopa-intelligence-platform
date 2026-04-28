import os
import sys
import argparse
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import get_database_url


REQUIRED_ENV = [
    "AZURE_SQL_SERVER",
    "AZURE_SQL_DATABASE",
    "AZURE_SQL_USERNAME",
    "AZURE_SQL_PASSWORD",
]


def masked_database_url() -> str:
    url = get_database_url()
    password = os.getenv("AZURE_SQL_PASSWORD")
    if password:
        url = url.replace(quote_plus(password), "****")
        url = url.replace(password, "****")
    return url


def pymssql_database_url(mask_password: bool = False) -> str:
    server = os.getenv("AZURE_SQL_SERVER")
    database = os.getenv("AZURE_SQL_DATABASE")
    username = quote_plus(os.getenv("AZURE_SQL_USERNAME", ""))
    password = quote_plus(os.getenv("AZURE_SQL_PASSWORD", ""))
    if mask_password:
        password = "****"
    return f"mssql+pymssql://{username}:{password}@{server}:1433/{database}"


def validate_env() -> None:
    missing = [name for name in REQUIRED_ENV if not os.getenv(name)]
    if missing:
        raise RuntimeError("Missing required Azure SQL env vars: " + ", ".join(missing))


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Azure SQL connectivity.")
    parser.add_argument(
        "--dialect",
        choices=["pyodbc", "pymssql"],
        default="pyodbc",
        help="Use pyodbc for production parity or pymssql for local diagnostics.",
    )
    args = parser.parse_args()

    os.environ["ENVIRONMENT"] = "production"
    validate_env()

    print("Azure SQL preflight")
    if args.dialect == "pymssql":
        database_url = pymssql_database_url()
        print(f"Connection: {pymssql_database_url(mask_password=True)}")
    else:
        database_url = get_database_url()
        print(f"Connection: {masked_database_url()}")

    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1")).scalar()
        if result != 1:
            raise RuntimeError("Unexpected SELECT 1 result")

    print("Azure SQL connectivity OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
