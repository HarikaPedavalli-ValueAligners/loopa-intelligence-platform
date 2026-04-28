import os
import sys
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


def validate_env() -> None:
    missing = [name for name in REQUIRED_ENV if not os.getenv(name)]
    if missing:
        raise RuntimeError("Missing required Azure SQL env vars: " + ", ".join(missing))


def main() -> int:
    os.environ["ENVIRONMENT"] = "production"
    validate_env()

    print("Azure SQL preflight")
    print(f"Connection: {masked_database_url()}")

    engine = create_engine(get_database_url(), pool_pre_ping=True)
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1")).scalar()
        if result != 1:
            raise RuntimeError("Unexpected SELECT 1 result")

    print("Azure SQL connectivity OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
