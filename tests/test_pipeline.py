"""Integration: build the whole dbt project against the committed sample.

Runs once per session (dbt build takes a few seconds). Skipped with a clear
message when dbt is not installed, so a plain `pytest` in a bare interpreter
still gives useful signal from the unit tests.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from pipeline import config
from pipeline.transform import DbtNotFound, run_dbt
from pipeline.warehouse import connect, fetch_one, load_bronze

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def demo_db(tmp_path_factory) -> Path:
    if not (shutil.which("dbt") or Path(sys.executable).with_name("dbt").exists()):
        pytest.skip("dbt is not installed; run `pip install -r requirements.txt`")

    db = tmp_path_factory.mktemp("warehouse") / "seismic.duckdb"
    rows = load_bronze(data_dir=config.ROOT / "data" / "sample", db_path=db)
    assert rows > 0, "sample lake is empty"
    try:
        run_dbt("build", db_path=db, quiet=True, full_refresh=True)
    except DbtNotFound:  # pragma: no cover - guarded above
        pytest.skip("dbt is not installed")
    return db


def test_warehouse_builds_and_reconciles(demo_db: Path):
    con = connect(read_only=True, db_path=demo_db)
    try:
        fact = fetch_one(con, "select count(*) as n from gold.fct_earthquakes")
        health = fetch_one(con, "select * from gold.mart_pipeline_health")
        assert fact["n"] > 0
        assert fact["n"] == health["valid_events"]
        assert health["duplicate_rows_removed"] == 0
        assert 25 <= health["coverage_days"] <= 31
    finally:
        con.close()


def test_every_event_has_local_time_and_region(demo_db: Path):
    con = connect(read_only=True, db_path=demo_db)
    try:
        row = fetch_one(
            con,
            """
            select
                count(*) as n,
                count(*) filter (where event_time_local is null) as null_local,
                count(*) filter (where region is null) as null_region,
                count(*) filter (where local_timezone not in ('Asia/Jakarta', 'Asia/Makassar', 'Asia/Jayapura')) as bad_tz
            from gold.fct_earthquakes
            """,
        )
        assert row["null_local"] == 0
        assert row["null_region"] == 0
        assert row["bad_tz"] == 0
    finally:
        con.close()


def test_magnitude_frequency_fit_is_plausible(demo_db: Path):
    con = connect(read_only=True, db_path=demo_db)
    try:
        row = fetch_one(
            con,
            """
            select b_value, r2, n_cumulative, mag_bin
            from gold.mart_magnitude_frequency
            where scope = 'national'
            order by mag_bin
            limit 1
            """,
        )
        assert 0.3 <= row["b_value"] <= 2.5
        assert row["r2"] >= 0.8
    finally:
        con.close()


def test_dashboard_renders_from_marts(demo_db: Path, tmp_path, monkeypatch):
    from pipeline.dashboard import render

    monkeypatch.setenv("SEISMIC_DASHBOARD_DIR", str(tmp_path))
    summary = render(db_path=demo_db)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    data = (tmp_path / "data.json").read_text(encoding="utf-8")

    assert summary["events"] > 0
    assert "Indonesian seismicity, modelled end to end" in html
    assert "<svg" in html
    assert "mart_pipeline_health" in html
    assert '"kpis"' in data
    assert "Luar wilayah" in html or "Province" in html
