"""Bronze layer: pull USGS FDSN events into immutable-ish JSON partitions.

Design notes
------------
* One folder per ingest day (``usgs/dt=YYYY-MM-DD/events.json``) is an
  ingestion-time partition, the same convention Iceberg/Hive use. Re-running
  the pipeline on the same day merges into that file instead of appending, so
  a retry is idempotent.
* Bronze keeps the raw USGS payload (GeoJSON) untouched. All typing, validation
  and deduplication happens later in the warehouse, which means a bug in a SQL
  model can never force us to re-download history.
* Every run is recorded in ``ops.pipeline_runs`` so the warehouse can report on
  its own health.
"""

from __future__ import annotations

import datetime as dt
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import requests

from . import config
from .util import atomic_write_json, date_windows, ensure_parent, utc_now


@dataclass
class IngestResult:
    start_date: dt.date
    end_date: dt.date
    started_at: dt.datetime
    finished_at: dt.datetime | None = None
    windows: int = 0
    events_fetched: int = 0
    events_in_bronze: int = 0
    files_written: list[str] = field(default_factory=list)
    status: str = "running"
    error: str | None = None

    @property
    def duration_seconds(self) -> float | None:
        if self.finished_at is None:
            return None
        return round((self.finished_at - self.started_at).total_seconds(), 2)


def fetch_window(
    start: dt.date,
    end: dt.date,
    *,
    session: requests.Session | None = None,
    retries: int = 3,
    timeout: int | None = None,
    min_magnitude: float | None = None,
) -> dict[str, Any]:
    """Fetch one inclusive date window from USGS as GeoJSON."""
    params = {
        "format": "geojson",
        "starttime": start.isoformat(),
        "endtime": end.isoformat(),
        "minmagnitude": str(min_magnitude if min_magnitude is not None else config.MIN_MAGNITUDE),
        "orderby": "time-asc",
        **config.BBOX,
    }
    client = session or requests.Session()
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = client.get(
                config.USGS_ENDPOINT,
                params=params,
                timeout=timeout or config.HTTP_TIMEOUT_SECONDS,
                headers={"User-Agent": config.USER_AGENT, "Accept": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("type") != "FeatureCollection":
                raise ValueError("unexpected payload: missing FeatureCollection")
            return payload
        except Exception as exc:  # noqa: BLE001 - retried and re-raised below
            last_error = exc
            if attempt < retries:
                time.sleep(2**attempt)
    raise RuntimeError(f"USGS request failed for {start}..{end}: {last_error}") from last_error


def merge_features(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Deduplicate by event id, keeping the most recently revised revision."""
    by_id: dict[str, dict[str, Any]] = {}
    for feature in existing:
        by_id[feature["id"]] = feature
    for feature in incoming:
        current = by_id.get(feature["id"])
        current_updated = (current or {}).get("properties", {}).get("updated") or 0
        incoming_updated = feature.get("properties", {}).get("updated") or 0
        if current is None or incoming_updated >= current_updated:
            by_id[feature["id"]] = feature
    return sorted(by_id.values(), key=lambda item: item["properties"]["time"])


def bronze_path(data_dir: Path, run_day: dt.date) -> Path:
    return data_dir / "usgs" / f"dt={run_day.isoformat()}" / "events.json"


def write_partition(
    payload_features: list[dict[str, Any]],
    run_day: dt.date,
    *,
    data_dir: Path | None = None,
    query: dict[str, Any] | None = None,
) -> Path:
    """Merge new features into today's partition and write it atomically."""
    target = bronze_path(data_dir or config.data_dir(), run_day)
    existing: list[dict[str, Any]] = []
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8")).get("features", [])
        except json.JSONDecodeError:
            existing = []  # a corrupt partition should not block a repair run
    features = merge_features(existing, payload_features)
    document = {
        "type": "FeatureCollection",
        "metadata": {
            "generated": int(utc_now().timestamp() * 1000),
            "count": len(features),
            "source": "USGS FDSN event API",
            "license": "USGS public domain",
            "query": query or {},
        },
        "features": features,
    }
    ensure_parent(target)
    atomic_write_json(target, document)
    return target


def record_run(result: IngestResult, *, db_path: Path | None = None) -> None:
    """Append the run to the ops table (best effort, never blocks the pipeline)."""
    try:
        resolved = (db_path or config.db_path()).resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(str(resolved))
        con.execute("create schema if not exists ops")
        con.execute(
            """
            create table if not exists ops.pipeline_runs (
                run_id        varchar,
                step          varchar,
                started_at    timestamptz,
                finished_at   timestamptz,
                status        varchar,
                row_count     bigint,
                duration_s    double,
                details       json
            )
            """
        )
        details = {
            "start_date": result.start_date.isoformat(),
            "end_date": result.end_date.isoformat(),
            "windows": result.windows,
            "events_fetched": result.events_fetched,
            "events_in_bronze": result.events_in_bronze,
            "files": result.files_written,
            "error": result.error,
        }
        con.execute(
            "insert into ops.pipeline_runs values (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                str(uuid.uuid4()),
                "ingest",
                result.started_at,
                result.finished_at,
                result.status,
                result.events_fetched,
                result.duration_seconds,
                json.dumps(details),
            ],
        )
        con.close()
    except Exception as exc:  # noqa: BLE001 - observability must not break ingest
        print(f"[warn] could not record run: {exc}")


def ingest(
    start: dt.date,
    end: dt.date,
    *,
    data_dir: Path | None = None,
    session: requests.Session | None = None,
    run_day: dt.date | None = None,
    record: bool = True,
) -> IngestResult:
    """Fetch ``start..end`` in windows and write them to the bronze lake."""
    result = IngestResult(start_date=start, end_date=end, started_at=utc_now())
    run_day = run_day or utc_now().date()
    client = session or requests.Session()
    try:
        windows = date_windows(start, end, config.WINDOW_DAYS)
        result.windows = len(windows)
        for window_start, window_end in windows:
            payload = fetch_window(window_start, window_end, session=client)
            features = payload.get("features", [])
            result.events_fetched += len(features)
            target = write_partition(
                features,
                run_day,
                data_dir=data_dir,
                query=payload.get("metadata", {}).get("url"),
            )
            if str(target) not in result.files_written:
                result.files_written.append(str(target))
            print(f"  {window_start}..{window_end}  {len(features):>4} events")
        result.events_in_bronze = sum(
            json.loads(Path(path).read_text(encoding="utf-8")).get("metadata", {}).get("count", 0)
            for path in result.files_written
        )
        result.status = "success"
    except Exception as exc:
        result.status = "failed"
        result.error = str(exc)
        raise
    finally:
        result.finished_at = utc_now()
        if record:
            record_run(result, db_path=config.db_path())
    return result
