# config.py
# Shared environment and database configuration for Loopa.

import os
from pathlib import Path
from urllib.parse import quote_plus


PROJECT_ROOT = Path(__file__).resolve().parent


try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


if load_dotenv:
    load_dotenv(PROJECT_ROOT / ".env")


def get_environment() -> str:
    """Returns the normalized runtime environment name."""
    return os.getenv("ENVIRONMENT", "development").strip().lower()


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_database_url() -> str:
    """
    Returns a SQLAlchemy database URL.

    DATABASE_URL takes precedence. Otherwise development uses SQLite and
    production uses Azure SQL credentials from the environment.
    """
    explicit_url = os.getenv("DATABASE_URL")
    if explicit_url:
        return explicit_url

    environment = get_environment()
    if environment in {"production", "prod", "azure"}:
        server = _required_env("AZURE_SQL_SERVER")
        database = _required_env("AZURE_SQL_DATABASE")
        username = quote_plus(_required_env("AZURE_SQL_USERNAME"))
        password = quote_plus(_required_env("AZURE_SQL_PASSWORD"))
        driver = quote_plus(os.getenv("AZURE_SQL_DRIVER", "ODBC Driver 18 for SQL Server"))
        port = os.getenv("AZURE_SQL_PORT", "1433")
        encrypt = os.getenv("AZURE_SQL_ENCRYPT", "yes")
        trust_server_certificate = os.getenv("AZURE_SQL_TRUST_SERVER_CERTIFICATE", "no")
        return (
            f"mssql+pyodbc://{username}:{password}@{server}:{port}/{database}"
            f"?driver={driver}"
            f"&Encrypt={encrypt}"
            f"&TrustServerCertificate={trust_server_certificate}"
        )

    sqlite_path = os.getenv("SQLITE_DB_PATH", "loopa_intelligence.db")
    db_path = Path(sqlite_path)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    return f"sqlite:///{db_path}"
