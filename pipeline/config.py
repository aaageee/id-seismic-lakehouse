"""Central configuration.

Every path is resolved lazily so the CLI, tests and CI can override locations
with environment variables without importing-order surprises.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Indonesia bounding box used for the USGS query (west of 94E we only get
# Sumatra's outer islands, east of 141.5E we lose nothing relevant).
BBOX = {
    "minlatitude": "-12.0",
    "maxlatitude": "6.5",
    "minlongitude": "94.0",
    "maxlongitude": "141.5",
}

USGS_ENDPOINT = "https://earthquake.usgs.gov/fdsnws/event/1/query"
MIN_MAGNITUDE = float(os.environ.get("SEISMIC_MIN_MAGNITUDE", "2.5"))
WINDOW_DAYS = int(os.environ.get("SEISMIC_WINDOW_DAYS", "31"))
HTTP_TIMEOUT_SECONDS = int(os.environ.get("SEISMIC_HTTP_TIMEOUT", "90"))
MAX_FRESHNESS_HOURS = int(os.environ.get("SEISMIC_MAX_FRESHNESS_HOURS", "72"))
USER_AGENT = "id-seismic-lakehouse/0.1 (+https://github.com/aaageee/id-seismic-lakehouse)"


def data_dir() -> Path:
    """Root of the bronze lake (ingestion-time partitions live below it)."""
    return Path(os.environ.get("SEISMIC_DATA_DIR", ROOT / "data" / "lake")).resolve()


def db_path() -> Path:
    return Path(os.environ.get("SEISMIC_DB", ROOT / "data" / "warehouse" / "seismic.duckdb")).resolve()


def dashboard_dir() -> Path:
    return Path(os.environ.get("SEISMIC_DASHBOARD_DIR", ROOT / "dashboard")).resolve()


def reports_dir() -> Path:
    return Path(os.environ.get("SEISMIC_REPORTS_DIR", ROOT / "reports")).resolve()
