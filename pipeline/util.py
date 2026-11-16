"""Small, dependency-free helpers shared by the pipeline stages."""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import tempfile
from pathlib import Path


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(ts: dt.datetime | None) -> str | None:
    if ts is None:
        return None
    return ts.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def date_windows(
    start: dt.date,
    end: dt.date,
    max_days: int = 31,
) -> list[tuple[dt.date, dt.date]]:
    """Split an inclusive date range into windows of at most ``max_days``.

    USGS caps a single FDSN response at 20k events; monthly windows keep the
    pipeline comfortably below that limit and make retries cheap.
    """
    if start > end:
        raise ValueError(f"start ({start}) is after end ({end})")
    if max_days < 1:
        raise ValueError("max_days must be >= 1")

    windows: list[tuple[dt.date, dt.date]] = []
    cursor = start
    while cursor <= end:
        window_end = min(cursor + dt.timedelta(days=max_days - 1), end)
        windows.append((cursor, window_end))
        cursor = window_end + dt.timedelta(days=1)
    return windows


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres (used by tests and notebooks)."""
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def atomic_write_text(path: Path, text: str) -> None:
    """Write via a temp file so a crashed run never leaves half a dashboard."""
    ensure_parent(path)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
        try:
            os.chmod(path, 0o644)
        except OSError:  # pragma: no cover - non-POSIX filesystems
            pass
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def atomic_write_json(path: Path, payload: object) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
