"""CLI entrypoint: ``python -m pipeline <command>``.

Commands are intentionally small and composable (the same way an orchestrator
would call them), so a failure at one stage never drags the others with it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

from . import config


def _parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def _resolve_window(args: argparse.Namespace) -> tuple[dt.date, dt.date]:
    if args.start or args.end:
        if not (args.start and args.end):
            raise SystemExit("--start and --end must be provided together")
        start, end = _parse_date(args.start), _parse_date(args.end)
    else:
        end = dt.date.today()
        start = end - dt.timedelta(days=args.days - 1)
    if start > end:
        raise SystemExit(f"start {start} is after end {end}")
    return start, end


def cmd_ingest(args: argparse.Namespace) -> int:
    from .ingest import ingest

    start, end = _resolve_window(args)
    print(f"[ingest] USGS M>={config.MIN_MAGNITUDE} {start} -> {end} ({args.days} days requested)")
    result = ingest(start, end)
    print(
        f"[ingest] {result.status}: {result.events_fetched} events fetched, "
        f"{result.events_in_bronze} in bronze, {result.duration_seconds}s"
    )
    return 0


def cmd_load(_: argparse.Namespace) -> int:
    from .warehouse import load_bronze

    rows = load_bronze()
    print(f"[load] bronze.usgs_events: {rows:,} raw feature rows")
    return 0


def cmd_transform(args: argparse.Namespace) -> int:
    from .transform import run_pipeline

    run_pipeline(full_refresh=args.full_refresh, select=args.select)
    return 0


def cmd_quality(_: argparse.Namespace) -> int:
    from .quality import run_checks, write_report

    checks, failed = run_checks()
    path = write_report(checks)
    for check in checks:
        print(f"  [{check['status']:<4}] {check['name']}: {check['value']}")
    print(f"[quality] report written to {path}")
    return 1 if failed else 0


def cmd_dashboard(_: argparse.Namespace) -> int:
    from .dashboard import render

    summary = render()
    print(f"[dashboard] {summary['path']} ({summary['events']:,} events)")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    from .dashboard import render
    from .quality import run_checks, write_report
    from .transform import run_pipeline
    from .warehouse import load_bronze

    if not args.skip_load:
        rows = load_bronze()
        print(f"[load] bronze.usgs_events: {rows:,} raw feature rows")
    run_pipeline(full_refresh=args.full_refresh, select=args.select)
    checks, _ = run_checks()
    report = write_report(checks)
    summary = render()
    print(f"[quality] {report}")
    print(f"[dashboard] {summary['path']} ({summary['events']:,} events)")
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    status = cmd_ingest(args)
    if status:
        return status
    return cmd_build(args)


def cmd_demo(args: argparse.Namespace) -> int:
    """Offline, reproducible build from the committed sample partition."""
    demo_root = config.ROOT / "build" / "demo"
    os.environ["SEISMIC_DATA_DIR"] = str(config.ROOT / "data" / "sample")
    os.environ["SEISMIC_DB"] = str(demo_root / "seismic.duckdb")
    os.environ["SEISMIC_DASHBOARD_DIR"] = str(demo_root / "dashboard")
    os.environ["SEISMIC_REPORTS_DIR"] = str(demo_root / "reports")
    args.skip_load = False
    args.full_refresh = True
    args.select = None
    print("[demo] offline build from data/sample (no network calls)")
    status = cmd_build(args)
    if status:
        return status
    print(f"[demo] open {demo_root / 'dashboard' / 'index.html'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="Indonesian seismicity lakehouse: ingest, model, publish.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Fetch USGS events into the bronze lake")
    ingest.add_argument("--days", type=int, default=365, help="Trailing window size (default: 365)")
    ingest.add_argument("--start", help="Inclusive start date (YYYY-MM-DD)")
    ingest.add_argument("--end", help="Inclusive end date (YYYY-MM-DD)")
    ingest.set_defaults(func=cmd_ingest)

    load = sub.add_parser("load", help="Load bronze JSON files into DuckDB")
    load.set_defaults(func=cmd_load)

    transform = sub.add_parser("transform", help="Run dbt build")
    transform.add_argument("--select", help="dbt selection expression")
    transform.add_argument("--full-refresh", action="store_true")
    transform.set_defaults(func=cmd_transform)

    build = sub.add_parser("build", help="Load, run dbt, check quality, render dashboard")
    build.add_argument("--select", help="dbt selection expression")
    build.add_argument("--full-refresh", action="store_true")
    build.add_argument("--skip-load", action="store_true")
    build.set_defaults(func=cmd_build)

    demo = sub.add_parser("demo", help="Offline build from the committed sample data")
    demo.set_defaults(func=cmd_demo, skip_load=False, full_refresh=False, select=None)

    all_cmd = sub.add_parser("all", help="Ingest then build")
    all_cmd.add_argument("--days", type=int, default=365)
    all_cmd.add_argument("--start")
    all_cmd.add_argument("--end")
    all_cmd.add_argument("--select")
    all_cmd.add_argument("--skip-load", action="store_true")
    all_cmd.add_argument("--full-refresh", action="store_true")
    all_cmd.set_defaults(func=cmd_all)

    dashboard = sub.add_parser("dashboard", help="Render dashboard/index.html from the marts")
    dashboard.set_defaults(func=cmd_dashboard)

    quality = sub.add_parser("quality", help="Run data-quality checks and write reports/quality.md")
    quality.set_defaults(func=cmd_quality)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
