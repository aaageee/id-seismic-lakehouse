"""Data-quality gate: read the health mart and publish a human report."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from . import config
from .util import atomic_write_text
from .warehouse import connect, fetch_all, fetch_one


def _status(ok: bool, *, warn: bool = False) -> str:
    if ok:
        return "PASS"
    return "WARN" if warn else "FAIL"


def run_checks(db_path: Path | None = None) -> tuple[list[dict[str, Any]], bool]:
    con = connect(read_only=True, db_path=db_path)
    try:
        health = fetch_one(con, "select * from gold.mart_pipeline_health")
        reconcile = fetch_one(
            con,
            """
            select
                (select count(*) from gold.fct_earthquakes)                                  as fct_rows,
                (select coalesce(sum(n_events), 0) from gold.mart_daily_activity)             as daily_rows,
                (select count(*) from gold.fct_earthquakes where region is null)               as null_region,
                (select count(*) from gold.fct_earthquakes where region_distance_km < 0)        as bad_distance,
                (select count(*) from gold.fct_earthquakes where magnitude < 0 or magnitude > 10) as bad_magnitude,
                (select count(*) from gold.fct_earthquakes where latitude not between -90 and 90) as bad_latitude,
                (select count(*) from gold.fct_earthquakes where longitude not between -180 and 180) as bad_longitude,
                (select max(event_time_utc) from gold.fct_earthquakes)                          as latest_event
            """,
        )
        fails = fetch_all(
            con,
            """
            select 'duplicate event ids' as check_name, count(*) as failures
            from (select event_id from gold.fct_earthquakes group by 1 having count(*) > 1)
            union all
            select 'future event timestamps', count(*)
            from gold.fct_earthquakes where event_time_utc > now() + interval 1 hour
            union all
            select 'magnitude-frequency scopes without fit', count(*)
            from gold.mart_magnitude_frequency
            where scope = 'national' and b_value is null
            """,
        )
    finally:
        con.close()

    total = int(reconcile.get("fct_rows") or 0)
    daily_total = int(reconcile.get("daily_rows") or 0)
    quarantined = int(health.get("quarantined_rows") or 0)
    quarantine_share = (quarantined / total) if total else 0.0
    latest = reconcile.get("latest_event")
    if isinstance(latest, str):
        latest = dt.datetime.fromisoformat(latest)
    age_hours = None
    if isinstance(latest, dt.datetime):
        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=dt.timezone.utc)
        age_hours = (dt.datetime.now(dt.timezone.utc) - latest).total_seconds() / 3600

    checks: list[dict[str, Any]] = [
        {
            "name": "Gold fact table is populated",
            "value": f"{total:,} events",
            "status": _status(total > 0),
        },
        {
            "name": "Daily mart reconciles with fact table",
            "value": f"{daily_total:,} vs {total:,}",
            "status": _status(total == daily_total),
        },
        {
            "name": "No duplicate event ids",
            "value": f"{int(fails[0]['failures']):,} duplicates",
            "status": _status(int(fails[0]["failures"]) == 0),
        },
        {
            "name": "Every event mapped to a region",
            "value": f"{int(reconcile.get('null_region') or 0):,} unmapped",
            "status": _status(int(reconcile.get("null_region") or 0) == 0),
        },
        {
            "name": "Coordinates inside valid ranges",
            "value": (
                f"{int(reconcile.get('bad_latitude') or 0):,} bad lat / "
                f"{int(reconcile.get('bad_longitude') or 0):,} bad lon"
            ),
            "status": _status(
                int(reconcile.get("bad_latitude") or 0) == 0
                and int(reconcile.get("bad_longitude") or 0) == 0
            ),
        },
        {
            "name": "Magnitudes inside 0-10",
            "value": f"{int(reconcile.get('bad_magnitude') or 0):,} out of range",
            "status": _status(int(reconcile.get("bad_magnitude") or 0) == 0),
        },
        {
            "name": "No future timestamps",
            "value": f"{int(fails[1]['failures']):,} future rows",
            "status": _status(int(fails[1]["failures"]) == 0),
        },
        {
            "name": "Quarantine rate below 10%",
            "value": f"{quarantine_share:.1%}",
            "status": _status(quarantine_share <= 0.10),
        },
        {
            "name": "b-value fitted for national scope",
            "value": f"{int(fails[2]['failures'])} missing fits",
            "status": _status(int(fails[2]["failures"]) == 0),
        },
        {
            "name": f"Data freshness (target < {config.MAX_FRESHNESS_HOURS}h)",
            "value": f"{age_hours:.1f} h" if age_hours is not None else "unknown",
            "status": _status(age_hours is not None and age_hours <= config.MAX_FRESHNESS_HOURS, warn=True),
        },
    ]
    failed = any(check["status"] == "FAIL" for check in checks)
    return checks, failed


def write_report(checks: list[dict[str, Any]], *, path: Path | None = None) -> Path:
    target = path or (config.reports_dir() / "quality.md")
    generated = dt.datetime.now().strftime("%d %b %Y %H:%M")
    passes = sum(1 for check in checks if check["status"] == "PASS")
    lines = [
        "# Data quality report",
        "",
        f"Generated: {generated} - {passes}/{len(checks)} checks passed.",
        "",
        "| # | Check | Observed | Result |",
        "|---|-------|----------|--------|",
    ]
    for idx, check in enumerate(checks, start=1):
        lines.append(f"| {idx} | {check['name']} | {check['value']} | **{check['status']}** |")
    lines += [
        "",
        "Checks run against the gold marts after `dbt build`. A `WARN` means the data is",
        "structurally valid but should be refreshed (for example when reviewing the",
        "committed demo sample, which is intentionally historical).",
        "",
    ]
    atomic_write_text(target, "\n".join(lines))
    return target
