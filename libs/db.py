import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv

import pyodbc

# .env next to repo root (works even if cwd isn't the project folder)
_REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_REPO_ROOT / ".env")


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _optional_env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None else value


def _ensure_sql_server_port(server: str) -> str:
    # Azure SQL host → tack on ,1433 if missing
    s = server.strip()
    if "," in s:
        return s
    if ".database.windows.net" in s.lower():
        return f"{s},1433"
    return s


def connection_string() -> str:
    # Full ODBC string wins; else build from DB_*
    direct = os.getenv("AZURE_SQL_CONNECTION_STRING")
    if direct and direct.strip():
        return direct.strip()

    server = os.getenv("DB_SERVER")
    database = os.getenv("DB_DATABASE")
    if not server or not str(server).strip():
        raise RuntimeError("Set AZURE_SQL_CONNECTION_STRING or DB_SERVER/DB_DATABASE in the environment")
    if not database or not str(database).strip():
        raise RuntimeError("Set AZURE_SQL_CONNECTION_STRING or DB_SERVER/DB_DATABASE in the environment")

    driver = _optional_env("DB_ODBC_DRIVER", "ODBC Driver 18 for SQL Server").strip() or "ODBC Driver 18 for SQL Server"
    username = _optional_env("DB_USERNAME", "")
    password = _optional_env("DB_PASSWORD", "")

    server_out = _ensure_sql_server_port(str(server).strip())
    database_out = str(database).strip()

    return (
        f"Driver={{{driver}}};"
        f"Server={server_out};"
        f"Database={database_out};"
        f"Uid={username};"
        f"Pwd={password};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
    )


@contextmanager
def cursor(*, autocommit: bool = True) -> Iterator[pyodbc.Cursor]:
    conn_str = connection_string()
    conn = pyodbc.connect(conn_str, autocommit=autocommit)
    try:
        cur = conn.cursor()
        try:
            yield cur
        finally:
            cur.close()
    finally:
        conn.close()


@contextmanager
def transaction() -> Iterator[pyodbc.Cursor]:
    """Single commit on success; rollback on error."""
    conn_str = connection_string()
    conn = pyodbc.connect(conn_str, autocommit=False)
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
