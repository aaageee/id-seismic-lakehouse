#!/usr/bin/env python3
"""Create the small committed sample used by `make demo` and CI.

The sample is a real slice of the USGS data (not synthetic), filtered to one
month so the repository stays light and `make demo` never touches the network.

Usage:
    python scripts/make_sample.py --start 2026-10-01 --end 2026-10-31
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.util import atomic_write_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2026-10-01")
    parser.add_argument("--end", default="2026-10-31")
    parser.add_argument("--lake-dir", default=str(ROOT / "data" / "lake"))
    parser.add_argument("--out-dir", default=str(ROOT / "data" / "sample"))
    parser.add_argument("--min-magnitude", type=float, default=2.5)
    args = parser.parse_args()

    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)
    start_ms = int(dt.datetime.combine(start, dt.time.min, dt.timezone.utc).timestamp() * 1000)
    end_ms = int(dt.datetime.combine(end, dt.time.max, dt.timezone.utc).timestamp() * 1000)

    features: dict[str, dict] = {}
    for path in sorted(Path(args.lake_dir).glob("usgs/dt=*/events.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        for feature in document.get("features", []):
            props = feature.get("properties", {})
            when = props.get("time")
            if when is None or not (start_ms <= when <= end_ms):
                continue
            if (props.get("mag") or 0) < args.min_magnitude:
                continue
            features[feature["id"]] = feature

    if not features:
        raise SystemExit("No features matched; run `make ingest` first.")

    ordered = sorted(features.values(), key=lambda item: item["properties"]["time"])
    target = Path(args.out_dir) / "usgs" / f"dt={end.isoformat()}" / "events.json"
    atomic_write_json(
        target,
        {
            "type": "FeatureCollection",
            "metadata": {
                "generated": int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000),
                "count": len(ordered),
                "source": "USGS FDSN event API",
                "license": "USGS public domain",
                "sample_window": {"start": start.isoformat(), "end": end.isoformat()},
                "note": "Committed sample for offline demo and CI. Regenerate with scripts/make_sample.py.",
            },
            "features": ordered,
        },
    )
    size_kb = target.stat().st_size / 1024
    print(f"wrote {len(ordered):,} events to {target} ({size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
