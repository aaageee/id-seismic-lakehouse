"""Serving layer: turn gold marts into one self-contained HTML dashboard."""

from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path
from typing import Any

from . import charts, config
from .util import atomic_write_json, atomic_write_text
from .warehouse import connect, fetch_all, fetch_one, humanize_age

MAG_COLORS = {
    "M2.5-3.9": "#38bdf8",
    "M4.0-4.9": "#facc15",
    "M5.0-5.9": "#fb923c",
    "M6.0+": "#ef4444",
}
DEPTH_COLORS = {
    "Shallow (<70 km)": "#f59e0b",
    "Intermediate (70-300 km)": "#60a5fa",
    "Deep (>300 km)": "#a78bfa",
}


def _fmt_int(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value):,.0f}"


def _fmt_num(value: Any, digits: int = 1) -> str:
    if value is None:
        return "-"
    return f"{float(value):,.{digits}f}"


def _fmt_time(value: Any, fmt: str = "%d %b %Y %H:%M") -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        try:
            value = dt.datetime.fromisoformat(value)
        except ValueError:
            return value
    return value.strftime(fmt)


def _magnitude_chip(magnitude: Any) -> str:
    if magnitude is None:
        return '<span class="chip">-</span>'
    value = float(magnitude)
    if value >= 6:
        color = MAG_COLORS["M6.0+"]
    elif value >= 5:
        color = MAG_COLORS["M5.0-5.9"]
    elif value >= 4:
        color = MAG_COLORS["M4.0-4.9"]
    else:
        color = MAG_COLORS["M2.5-3.9"]
    return (
        f'<span class="chip" style="--chip:{color}">'
        f"{value:.1f}</span>"
    )


def _load_datasets(db_path: Path | None = None) -> dict[str, Any]:
    con = connect(read_only=True, db_path=db_path)
    try:
        kpis = fetch_one(
            con,
            """
            select
                count(*)                                        as n_events,
                max(magnitude)                                  as max_magnitude,
                count(*) filter (where magnitude >= 5)          as n_m5,
                count(*) filter (where magnitude >= 6)          as n_m6,
                count(*) filter (where tsunami)                 as n_tsunami,
                count(*) filter (where tsunami)                 as n_tsunami,
                count(distinct region) filter (where region <> 'Luar wilayah') as n_regions,
                min(event_time_local)                           as first_event,
                max(event_time_local)                           as latest_event,
                avg(depth_km)                                   as avg_depth_km,
                sum(energy_tons_tnt)                            as total_energy_tons
            from gold.fct_earthquakes
            """
        )
        daily = fetch_all(
            con,
            """
            select * from gold.mart_daily_activity
            order by activity_date desc
            limit 150
            """,
        )
        daily.reverse()
        regions = fetch_all(
            con,
            """
            select region, island, n_events, max_magnitude, n_m5plus, avg_depth_km,
                   days_since_m5, b_value
            from gold.mart_region_activity
            order by n_events desc, max_magnitude desc
            limit 12
            """,
        )
        mfd = fetch_all(
            con,
            """
            select mag_bin, n_cumulative
            from gold.mart_magnitude_frequency
            where scope = 'national'
            order by mag_bin
            """,
        )
        mfd_meta = fetch_one(
            con,
            """
            select b_value, r2, mc, n_events_above_mc
            from gold.mart_magnitude_frequency
            where scope = 'national'
            limit 1
            """,
        )
        depth = fetch_all(con, "select * from gold.mart_depth_profile order by min_depth_km")
        latest = fetch_all(
            con,
            """
            select event_time_local, local_timezone, magnitude, depth_km, region, place, tsunami, source_url
            from gold.fct_earthquakes
            order by event_time_utc desc
            limit 12
            """,
        )
        health = fetch_one(con, "select * from gold.mart_pipeline_health")
    finally:
        con.close()

    return {
        "kpis": kpis,
        "daily": daily,
        "regions": regions,
        "mfd": mfd,
        "mfd_meta": mfd_meta,
        "depth": depth,
        "latest": latest,
        "health": health,
    }


CSS = """
:root {
  --bg: #0b1017;
  --panel: #131b26;
  --panel-2: #0f1620;
  --border: #223042;
  --text: #e6edf3;
  --muted: #93a4b8;
  --accent: #f59e0b;
  --grid: #223042;
  color-scheme: dark;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: radial-gradient(1200px 600px at 15% -10%, #1b2a3d 0%, var(--bg) 55%) no-repeat, var(--bg);
  color: var(--text);
  font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Inter, Roboto, sans-serif;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1180px; margin: 0 auto; padding: 40px 24px 64px; }
.eyebrow { color: var(--accent); font-size: 11.5px; letter-spacing: .16em; text-transform: uppercase; font-weight: 650; }
h1 { font-size: clamp(28px, 4vw, 42px); line-height: 1.1; margin: 10px 0 10px; letter-spacing: -.02em; }
h2 { font-size: 15px; margin: 0 0 2px; letter-spacing: -.01em; }
.sub { color: var(--muted); max-width: 720px; margin: 0 0 18px; }
.meta { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 28px; }
.pill {
  border: 1px solid var(--border); background: var(--panel);
  border-radius: 999px; padding: 5px 12px; font-size: 12px; color: var(--muted);
}
.pill b { color: var(--text); font-weight: 600; }
.pill.live::before {
  content: ""; display: inline-block; width: 7px; height: 7px; border-radius: 50%;
  background: #22c55e; margin-right: 7px; box-shadow: 0 0 0 3px rgba(34,197,94,.15);
}
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-bottom: 22px; }
.kpi {
  background: linear-gradient(180deg, var(--panel) 0%, var(--panel-2) 100%);
  border: 1px solid var(--border); border-radius: 14px; padding: 15px 16px;
}
.kpi .label { color: var(--muted); font-size: 11.5px; letter-spacing: .05em; text-transform: uppercase; }
.kpi .value { font-size: 27px; font-weight: 680; letter-spacing: -.02em; margin-top: 6px; font-variant-numeric: tabular-nums; }
.kpi .hint { color: var(--muted); font-size: 11.5px; margin-top: 2px; }
.kpi.warn .value { color: var(--accent); }
.grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 14px; }
.card {
  background: var(--panel); border: 1px solid var(--border); border-radius: 16px;
  padding: 16px 18px; overflow: hidden;
}
.card.wide { grid-column: span 12; }
.card.half { grid-column: span 6; }
.card.third { grid-column: span 4; }
@media (max-width: 900px) {
  .card.half, .card.third { grid-column: span 12; }
  .wrap { padding: 28px 16px 48px; }
}
.card-head { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; margin-bottom: 4px; }
.card-head .note { color: var(--muted); font-size: 11.5px; }
.chart { width: 100%; height: auto; display: block; margin-top: 6px; }
.axis { fill: var(--muted); font-size: 10px; font-variant-numeric: tabular-nums; }
.axis-label { fill: var(--muted); font-size: 10px; letter-spacing: .04em; }
.bar-label { fill: var(--text); font-size: 11.5px; }
.bar-value { fill: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums; }
.b-value { fill: var(--accent); font-size: 12px; font-weight: 650; }
.donut-wrap { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; }
.donut { width: 190px; height: 190px; flex: 0 0 auto; }
.donut-value { fill: var(--text); font-size: 24px; font-weight: 680; }
.donut-label { fill: var(--muted); font-size: 10.5px; letter-spacing: .06em; text-transform: uppercase; }
.legend { list-style: none; padding: 0; margin: 0; flex: 1 1 150px; }
.legend li { display: grid; grid-template-columns: 10px 1fr auto auto; gap: 8px; align-items: center; padding: 4px 0; font-size: 12px; }
.legend .dot { width: 8px; height: 8px; border-radius: 2px; }
.legend-label { color: var(--muted); }
.legend-value { font-variant-numeric: tabular-nums; }
.legend-share { color: var(--muted); width: 34px; text-align: right; font-variant-numeric: tabular-nums; }
table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
th { text-align: left; color: var(--muted); font-weight: 550; font-size: 10.5px; letter-spacing: .06em; text-transform: uppercase; padding: 8px 8px; border-bottom: 1px solid var(--border); }
td { padding: 8px 8px; border-bottom: 1px solid rgba(34,48,66,.55); vertical-align: middle; }
tr:last-child td { border-bottom: none; }
td.num { font-variant-numeric: tabular-nums; color: var(--muted); }
td a { color: var(--text); text-decoration: none; border-bottom: 1px dotted var(--border); }
td a:hover { border-bottom-color: var(--accent); }
.chip {
  display: inline-flex; min-width: 38px; justify-content: center; align-items: center;
  border-radius: 6px; padding: 2px 6px; font-weight: 650; font-size: 11.5px;
  color: var(--chip, var(--text)); background: color-mix(in srgb, var(--chip, #64748b) 16%, transparent);
  border: 1px solid color-mix(in srgb, var(--chip, #64748b) 35%, transparent);
  font-variant-numeric: tabular-nums;
}
.tsunami { color: #f87171; font-weight: 650; font-size: 11px; }
.muted { color: var(--muted); }
.quality { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-top: 10px; }
.q-item { border: 1px solid var(--border); border-radius: 10px; padding: 9px 11px; background: var(--panel-2); }
.q-item .label { color: var(--muted); font-size: 10.5px; text-transform: uppercase; letter-spacing: .05em; }
.q-item .value { font-size: 16px; font-weight: 620; font-variant-numeric: tabular-nums; margin-top: 2px; }
footer { margin-top: 26px; color: var(--muted); font-size: 12px; display: flex; flex-wrap: wrap; gap: 10px; justify-content: space-between; }
footer a { color: var(--text); text-decoration: none; border-bottom: 1px dotted var(--border); }
.empty { color: var(--muted); font-size: 12.5px; }
details { margin-top: 10px; color: var(--muted); font-size: 12px; }
details summary { cursor: pointer; color: var(--text); }
.method { margin-top: 8px; padding-left: 18px; }
.method li { margin: 4px 0; }
"""


def render(db_path: Path | None = None) -> dict[str, Any]:
    data = _load_datasets(db_path)
    kpis = data["kpis"] or {}
    health = data["health"] or {}

    daily_rows = [
        {
            "date": row["activity_date"].isoformat() if hasattr(row["activity_date"], "isoformat") else str(row["activity_date"]),
            "M2.5-3.9": row["n_m25_39"],
            "M4.0-4.9": row["n_m40_49"],
            "M5.0-5.9": row["n_m50_59"],
            "M6.0+": row["n_m60plus"],
        }
        for row in data["daily"]
    ]
    daily_svg = charts.stacked_bars(
        daily_rows,
        keys=list(MAG_COLORS.keys()),
        colors=list(MAG_COLORS.values()),
        legend=list(MAG_COLORS.keys()),
        aria_label="Daily earthquake counts by magnitude class",
    )

    mfd_points = [(float(row["mag_bin"]), float(row["n_cumulative"])) for row in data["mfd"]]
    b_value = data["mfd_meta"].get("b_value") if data["mfd_meta"] else None
    r2 = data["mfd_meta"].get("r2") if data["mfd_meta"] else None
    mc = data["mfd_meta"].get("mc") if data["mfd_meta"] else None
    mfd_svg = charts.log_line(mfd_points, b_value=b_value)

    region_items = [(row["region"], row["n_events"]) for row in data["regions"]]
    region_svg = charts.hbar(region_items, aria_label="Most active regions")

    depth_items = [
        (row["depth_class"], row["n_events"], DEPTH_COLORS.get(row["depth_class"], "#64748b"))
        for row in data["depth"]
    ]
    depth_svg = charts.donut(
        depth_items,
        center_label="earthquakes",
        center_value=_fmt_int(kpis.get("n_events")),
        aria_label="Depth distribution",
    )

    latest_rows = []
    tz_labels = {"Asia/Jakarta": "WIB", "Asia/Makassar": "WITA", "Asia/Jayapura": "WIT"}
    for row in data["latest"]:
        tsunami_flag = '<span class="tsunami">YES</span>' if row["tsunami"] else ""
        tz_label = tz_labels.get(str(row["local_timezone"]), "")
        place = html.escape(str(row["place"]))
        if row.get("source_url"):
            place = (
                f'<a href="{html.escape(str(row["source_url"]), quote=True)}" '
                f'target="_blank" rel="noopener">{place}</a>'
            )
        latest_rows.append(
            "<tr>"
            f'<td class="num">{html.escape(_fmt_time(row["event_time_local"], "%d %b %H:%M"))} {tz_label}</td>'
            f"<td>{_magnitude_chip(row['magnitude'])}</td>"
            f'<td class="num">{_fmt_num(row["depth_km"], 0)} km</td>'
            f'<td>{html.escape(str(row["region"]))}</td>'
            f'<td class="muted">{place}</td>'
            f"<td>{tsunami_flag}</td>"
            "</tr>"
        )

    region_rows = []
    for row in data["regions"][:8]:
        region_rows.append(
            "<tr>"
            f'<td>{html.escape(str(row["region"]))}</td>'
            f'<td class="muted">{html.escape(str(row["island"]))}</td>'
            f'<td class="num">{_fmt_int(row["n_events"])}</td>'
            f'<td class="num">{_fmt_num(row["max_magnitude"], 1)}</td>'
            f'<td class="num">{_fmt_int(row["n_m5plus"])}</td>'
            f'<td class="num">{_fmt_num(row["avg_depth_km"], 0)} km</td>'
            f'<td class="num">{_fmt_num(row["b_value"], 2)}</td>'
            "</tr>"
        )

    window_start = _fmt_time(kpis.get("first_event"), "%d %b %Y")
    window_end = _fmt_time(kpis.get("latest_event"), "%d %b %Y")
    coverage_days = health.get("coverage_days") or "-"
    generated_at = _fmt_time(dt.datetime.now(), "%d %b %Y %H:%M")
    latest_age = humanize_age(kpis.get("latest_event"))

    plain_latest = [_jsonable(row) for row in data["latest"]]
    payload = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "window": {"start": window_start, "end": window_end, "coverage_days": coverage_days},
        "kpis": {key: _jsonable(value) for key, value in kpis.items()},
        "health": {key: _jsonable(value) for key, value in health.items()},
        "regions": [_jsonable(row) for row in data["regions"]],
        "daily": [_jsonable(row) for row in data["daily"]],
        "magnitude_frequency": [_jsonable(row) for row in data["mfd"]],
        "b_value": _jsonable(b_value),
        "depth_profile": [_jsonable(row) for row in data["depth"]],
        "latest_events": plain_latest,
    }

    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Indonesian Seismicity Lakehouse - live marts</title>
<meta name="description" content="Daily-updated earthquake analytics for Indonesia, built with Python, DuckDB and dbt.">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="eyebrow">Data engineering portfolio &middot; Project 01</div>
  <h1>Indonesian seismicity, modelled end to end</h1>
  <p class="sub">
    Bronze from the USGS FDSN API, silver in DuckDB, gold marts in dbt.
    Every number below is queried live from the warehouse at build time &mdash; no hand-made charts.
  </p>

  <div class="meta">
    <span class="pill live">latest event <b>{html.escape(str(latest_age))}</b></span>
    <span class="pill">window <b>{html.escape(str(window_start))} &rarr; {html.escape(str(window_end))}</b></span>
    <span class="pill">coverage <b>{html.escape(str(coverage_days))} days</b></span>
    <span class="pill">events <b>{_fmt_int(kpis.get("n_events"))}</b></span>
    <span class="pill">source <b>USGS FDSN</b></span>
  </div>

  <section class="kpis">
    <div class="kpi">
      <div class="label">Detected events</div>
      <div class="value">{_fmt_int(kpis.get("n_events"))}</div>
      <div class="hint">M&ge;2.5 inside the Indonesian bbox</div>
    </div>
    <div class="kpi">
      <div class="label">Largest magnitude</div>
      <div class="value">{_fmt_num(kpis.get("max_magnitude"), 1)}</div>
      <div class="hint">{_fmt_int(kpis.get("n_m6"))} events at M6+</div>
    </div>
    <div class="kpi">
      <div class="label">M5+ events</div>
      <div class="value">{_fmt_int(kpis.get("n_m5"))}</div>
      <div class="hint">felt widely, monitored closely</div>
    </div>
    <div class="kpi {'warn' if (kpis.get("n_tsunami") or 0) > 0 else ''}">
      <div class="label">Tsunami flags</div>
      <div class="value">{_fmt_int(kpis.get("n_tsunami"))}</div>
      <div class="hint">USGS tsunami bulletins</div>
    </div>
    <div class="kpi">
      <div class="label">Provinces affected</div>
      <div class="value">{_fmt_int(kpis.get("n_regions"))}</div>
      <div class="hint">nearest-capital assignment</div>
    </div>
  </section>

  <div class="grid">
    <div class="card wide">
      <div class="card-head">
        <div>
          <h2>Daily seismicity</h2>
          <span class="note">last {_fmt_int(len(daily_rows))} days, stacked by magnitude class</span>
        </div>
        <span class="note">avg depth {_fmt_num(kpis.get("avg_depth_km"), 0)} km</span>
      </div>
      {daily_svg}
    </div>

    <div class="card half">
      <div class="card-head">
        <div>
          <h2>Magnitude&ndash;frequency</h2>
          <span class="note">Gutenberg&ndash;Richter, M&ge;{_fmt_num(mc, 1) if mc else "-"}</span>
        </div>
        <span class="note">R&sup2; {_fmt_num(r2, 3) if r2 is not None else "-"}</span>
      </div>
      {mfd_svg}
    </div>

    <div class="card third">
      <div class="card-head">
        <div>
          <h2>Depth profile</h2>
          <span class="note">subduction vs. crustal</span>
        </div>
      </div>
      <div class="donut-wrap">{depth_svg}</div>
    </div>

    <div class="card half">
      <div class="card-head">
        <div>
          <h2>Most active provinces</h2>
          <span class="note">events over the coverage window</span>
        </div>
      </div>
      {region_svg}
    </div>

    <div class="card half">
      <div class="card-head">
        <div>
          <h2>Regional detail</h2>
          <span class="note">b-value needs 40+ events above Mc</span>
        </div>
      </div>
      <table>
        <thead><tr><th>Province</th><th>Island</th><th>Events</th><th>Max M</th><th>M5+</th><th>Avg depth</th><th>b</th></tr></thead>
        <tbody>{''.join(region_rows)}</tbody>
      </table>
    </div>

    <div class="card wide">
      <div class="card-head">
        <div>
          <h2>Latest events</h2>
          <span class="note">local time per event time zone, straight from <code>fct_earthquakes</code></span>
        </div>
        <span class="note">total energy {_fmt_num(kpis.get("total_energy_tons"), 0)} t TNT</span>
      </div>
      <table>
        <thead><tr><th>Time</th><th>M</th><th>Depth</th><th>Province</th><th>USGS place</th><th></th></tr></thead>
        <tbody>{''.join(latest_rows)}</tbody>
      </table>
    </div>

    <div class="card wide">
      <div class="card-head">
        <div>
          <h2>Pipeline health</h2>
          <span class="note">measured in <code>mart_pipeline_health</code>, tested in CI</span>
        </div>
        <span class="note">generated {html.escape(generated_at)}</span>
      </div>
      <div class="quality">
        <div class="q-item"><div class="label">Raw rows</div><div class="value">{_fmt_int(health.get("total_raw_rows"))}</div></div>
        <div class="q-item"><div class="label">Deduped</div><div class="value">{_fmt_int(health.get("latest_revision_rows"))}</div></div>
        <div class="q-item"><div class="label">Duplicates dropped</div><div class="value">{_fmt_int(health.get("duplicate_rows_removed"))}</div></div>
        <div class="q-item"><div class="label">Quarantined</div><div class="value">{_fmt_int(health.get("quarantined_rows"))}</div></div>
        <div class="q-item"><div class="label">Bronze files</div><div class="value">{_fmt_int(health.get("ingest_files"))}</div></div>
        <div class="q-item"><div class="label">Last ingest</div><div class="value">{html.escape(str(health.get("last_ingest_date") or "-"))}</div></div>
      </div>
      <details>
        <summary>How the numbers are produced</summary>
        <ul class="method">
          <li>Ingest splits the window into 31-day requests, writes raw GeoJSON per ingest day, and merges retries by event id.</li>
          <li>Staging explodes the GeoJSON feature list, keeps the latest USGS revision and flags invalid rows into a quarantine model.</li>
          <li>Intermediate assigns each event to the nearest provincial capital (haversine) and converts UTC to WIB / WITA / WIT.</li>
          <li>Energy uses the Gutenberg&ndash;Richter magnitude&ndash;energy relation: log10(E) = 4.8 + 1.5M, reported in tons of TNT.</li>
          <li>b-value is a least-squares fit of log10(N&ge;M) on M, using events at or above the completeness magnitude Mc.</li>
        </ul>
      </details>
    </div>
  </div>

  <footer>
    <span>Source: <a href="https://earthquake.usgs.gov/fdsnws/event/1/">USGS FDSN event API</a> (public domain). Not an official early-warning product.</span>
    <span>Python &middot; DuckDB &middot; dbt &middot; GitHub Actions</span>
  </footer>
</div>
</body>
</html>
"""

    target_dir = config.dashboard_dir()
    atomic_write_text(target_dir / "index.html", document)
    atomic_write_json(target_dir / "data.json", payload)
    return {
        "path": str(target_dir / "index.html"),
        "events": int(kpis.get("n_events") or 0),
        "window": {"start": window_start, "end": window_end},
        "b_value": b_value,
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dt.timedelta):
        return value.total_seconds()
    return value


if __name__ == "__main__":  # pragma: no cover
    print(json.dumps(render(), indent=2))
