"""DuckDB access layer.

One process may write to the database file at a time; pass read_only=True for
concurrent readers (e.g. notebooks open while a pipeline runs).
"""
from __future__ import annotations

import duckdb

from .config import DB_PATH, SQL_DIR


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DB_PATH), read_only=read_only)


def init_db(con: duckdb.DuckDBPyConnection | None = None) -> None:
    """Apply sql/schema.sql. Fails if tables already exist (drop the .duckdb
    file to rebuild from scratch — everything is replayable from data/raw)."""
    schema_sql = (SQL_DIR / "schema.sql").read_text(encoding="utf-8")
    owned = con is None
    con = con or connect()
    try:
        con.execute(schema_sql)
    finally:
        if owned:
            con.close()
