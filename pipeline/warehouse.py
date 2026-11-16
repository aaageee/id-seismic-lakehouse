"""Warehouse helpers: load the bronze lake into DuckDB and read from it."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import duckdb

from . import config


def connect(*, read_only: bool = False, db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    path = (db_path or config.db_path()).resolve()
    if not read_only:
        path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path), read_only=read_only)


def fetch_all(con: duckdb.DuckDBPyConnection, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    cursor = con.execute(sql, params or [])
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]


def fetch_one(con: duckdb.DuckDBPyConnection, sql: str, params: list[Any] | None = None) -> dict[str, Any]:
    rows = fetch_all(con, sql, params)
    return rows[0] if rows else {}


def bronze_files(data_dir: Path | None = None) -> list[Path]:
    return sorted((data_dir or config.data_dir()).glob("usgs/dt=*/events.json"))


def load_bronze(
    *,
    data_dir: Path | None = None,
    db_path: Path | None = None,
) -> int:
    """Replace ``bronze.usgs_events`` with everything currently in the lake.

    At a few thousand events per year a full replace is cheaper and far easier
    to reason about than incremental merges. The expensive part (the API call)
    is already cached in JSON files, so this is a sub-second operation.
    """
    files = bronze_files(data_dir)
    if not files:
        raise FileNotFoundError(
            "No bronze files found. Run `make ingest` (or `make demo` for the committed sample)."
        )

    glob = str((data_dir or config.data_dir()) / "usgs" / "dt=*" / "events.json")
    glob_literal = glob.replace("'", "''")

    con = connect(db_path=db_path)
    try:
        con.execute("create schema if not exists bronze")
        con.execute(
            f"""
            create or replace table bronze.usgs_events as
            select
                *,
                filename as _source_file,
                regexp_extract(filename, 'dt=([0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}})', 1) as _ingest_date,
                now() as _loaded_at
            from read_json_auto(
                '{glob_literal}',
                union_by_name = true,
                filename = true,
                sample_size = -1
            )
            """
        )
        rows = con.execute(
            "select count(*) from bronze.usgs_events, unnest(bronze.usgs_events.features)"
        ).fetchone()[0]
    finally:
        con.close()
    return int(rows)


def latest_ingest_run(db_path: Path | None = None) -> dict[str, Any]:
    con = connect(read_only=False, db_path=db_path)
    try:
        exists = con.execute(
            "select count(*) from information_schema.tables where table_schema = 'ops' and table_name = 'pipeline_runs'"
        ).fetchone()[0]
        if not exists:
            return {}
        return fetch_one(
            con,
            """
            select step, started_at, finished_at, status, row_count, duration_s, details
            from ops.pipeline_runs
            order by started_at desc
            limit 1
            """,
        )
    finally:
        con.close()


def parse_details(value: Any) -> dict[str, Any]:
    """DuckDB returns JSON columns as ``str``; normalise for callers."""
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    import json

    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return {}


def humanize_age(ts: dt.datetime | None) -> str:
    if ts is None:
        return "unknown"
    if isinstance(ts, str):
        ts = dt.datetime.fromisoformat(ts)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    delta = dt.datetime.now(dt.timezone.utc) - ts.astimezone(dt.timezone.utc)
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} h ago"
    return f"{hours // 24} days ago"
