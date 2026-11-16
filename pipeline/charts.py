"""Tiny dependency-free SVG chart kit.

The dashboard is a single static HTML file, so charts are rendered at build
time as inline SVG. No JavaScript, no CDN, works offline and inside GitHub
Pages without any build step.
"""

from __future__ import annotations

import datetime as dt
import html
import math
from collections.abc import Iterable, Sequence


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _nice_max(value: float) -> float:
    if value <= 0:
        return 1.0
    exponent = math.floor(math.log10(value))
    base = 10**exponent
    for step in (1, 2, 2.5, 5, 10):
        if value <= step * base:
            return step * base
    return 10 * base


def _format_int(value: float) -> str:
    return f"{value:,.0f}"


def _date_label(value: str, fmt: str = "%d %b") -> str:
    try:
        return dt.date.fromisoformat(value).strftime(fmt)
    except (ValueError, TypeError):
        return str(value)


def stacked_bars(
    rows: Sequence[dict],
    *,
    keys: Sequence[str],
    colors: Sequence[str],
    legend: Sequence[str] | None = None,
    width: int = 820,
    height: int = 252,
    aria_label: str = "Stacked bar chart",
) -> str:
    """Stacked daily counts. ``rows`` must contain ``date`` plus one key per series."""
    if not rows:
        return '<p class="empty">No data</p>'

    left, right, top, bottom = 44, 12, 16, 50
    plot_w = width - left - right
    plot_h = height - top - bottom

    totals = [sum(float(row.get(key) or 0) for key in keys) for row in rows]
    y_max = _nice_max(max(totals) if totals else 1)
    slot = plot_w / len(rows)
    bar_w = max(1.0, slot * 0.72)

    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(aria_label)}" '
        f'preserveAspectRatio="none">'
    ]

    # y grid + labels
    for idx in range(5):
        value = y_max * idx / 4
        y = top + plot_h - plot_h * idx / 4
        parts.append(
            f'<line x1="{left}" x2="{width - right}" y1="{y:.1f}" y2="{y:.1f}" '
            f'stroke="var(--grid)" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{left - 8}" y="{y + 3.5:.1f}" text-anchor="end" '
            f'class="axis">{_format_int(value)}</text>'
        )

    for idx, row in enumerate(rows):
        x = left + idx * slot + (slot - bar_w) / 2
        y_cursor = top + plot_h
        for key, color in zip(keys, colors, strict=True):
            value = float(row.get(key) or 0)
            if value <= 0:
                continue
            segment = plot_h * value / y_max
            y_cursor -= segment
            label = f"{row['date']}: {key}={int(value)}"
            parts.append(
                f'<rect x="{x:.1f}" y="{y_cursor:.1f}" width="{bar_w:.1f}" height="{segment:.1f}" '
                f'fill="{color}" rx="1"><title>{esc(label)}</title></rect>'
            )

    label_every = max(1, math.ceil(len(rows) / 7))
    for idx, row in enumerate(rows):
        if idx % label_every:
            continue
        x = left + idx * slot + slot / 2
        parts.append(
            f'<text x="{x:.1f}" y="{height - 30}" text-anchor="middle" class="axis">'
            f"{esc(_date_label(row['date']))}</text>"
        )

    if legend:
        for idx, (text, color) in enumerate(zip(legend, colors, strict=False)):
            x = left + idx * 132
            parts.append(f'<rect x="{x}" y="{height - 12}" width="8" height="8" fill="{color}" rx="2"/>')
            parts.append(f'<text x="{x + 12}" y="{height - 5}" class="axis">{esc(text)}</text>')

    parts.append("</svg>")
    return "".join(parts)


def log_line(
    points: Sequence[tuple[float, float]],
    *,
    width: int = 400,
    height: int = 240,
    color: str = "#f59e0b",
    b_value: float | None = None,
    aria_label: str = "Magnitude frequency distribution",
) -> str:
    """Gutenberg-Richter plot: magnitude (x) vs cumulative count (log10 y)."""
    if not points:
        return '<p class="empty">Not enough events to fit a curve.</p>'

    left, right, top, bottom = 46, 14, 18, 34
    plot_w = width - left - right
    plot_h = height - top - bottom

    xs = [float(x) for x, _ in points]
    ys = [max(float(y), 1.0) for _, y in points]
    x_min, x_max = min(xs), max(xs)
    if x_max == x_min:
        x_max = x_min + 1
    y_min, y_max = 0.0, math.log10(max(ys) * 1.35)

    def sx(x: float) -> float:
        return left + plot_w * (x - x_min) / (x_max - x_min)

    def sy(y: float) -> float:
        return top + plot_h - plot_h * (math.log10(max(y, 1.0)) - y_min) / (y_max - y_min)

    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(aria_label)}">'
    ]

    # horizontal log grid
    grid_values = [value for value in (1, 10, 100, 1000, 10000) if math.log10(value) <= y_max]
    for value in grid_values:
        y = sy(value)
        parts.append(
            f'<line x1="{left}" x2="{width - right}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--grid)"/>'
        )
        parts.append(
            f'<text x="{left - 8}" y="{y + 3.5:.1f}" text-anchor="end" class="axis">{_format_int(value)}</text>'
        )

    path = " ".join(
        f"{'M' if idx == 0 else 'L'}{sx(x):.1f},{sy(y):.1f}" for idx, (x, y) in enumerate(points)
    )
    parts.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linejoin="round"/>')
    for x, y in points:
        parts.append(
            f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="2.6" fill="{color}">'
            f"<title>M {x:.1f}: {_format_int(y)} events</title></circle>"
        )

    # x ticks at bin edges
    tick_every = max(1, math.ceil(len(xs) / 6))
    for idx in range(0, len(xs), tick_every):
        parts.append(
            f'<text x="{sx(xs[idx]):.1f}" y="{height - 14}" text-anchor="middle" class="axis">'
            f"M{xs[idx]:.1f}</text>"
        )

    parts.append(
        f'<text x="{left}" y="{height - 2}" class="axis-label">Magnitude (M)</text>'
    )
    parts.append(
        f'<text x="{width - right}" y="{top - 4}" text-anchor="end" class="axis-label">'
        "cumulative events (log)</text>"
    )
    if b_value is not None:
        parts.append(
            f'<text x="{width - right}" y="{top + 16}" text-anchor="end" class="b-value">'
            f"b = {b_value:.2f}</text>"
        )
    parts.append("</svg>")
    return "".join(parts)


def hbar(
    items: Sequence[tuple[str, float]],
    *,
    width: int = 460,
    color: str = "#f59e0b",
    unit: str = "events",
    aria_label: str = "Horizontal bar chart",
) -> str:
    if not items:
        return '<p class="empty">No data</p>'

    row_h = 28
    height = row_h * len(items) + 12
    label_w = 150
    value_w = 44
    plot_w = width - label_w - value_w
    maximum = max(value for _, value in items) or 1

    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(aria_label)}">'
    ]
    for idx, (label, value) in enumerate(items):
        y = 6 + idx * row_h
        bar_w = max(2.0, plot_w * float(value) / maximum)
        short = label if len(label) <= 22 else label[:20] + "..."
        parts.append(
            f'<text x="0" y="{y + 14}" class="bar-label">{esc(short)}</text>'
        )
        parts.append(
            f'<rect x="{label_w}" y="{y + 3}" width="{plot_w}" height="14" fill="var(--grid)" rx="4"/>'
        )
        parts.append(
            f'<rect x="{label_w}" y="{y + 3}" width="{bar_w:.1f}" height="14" fill="{color}" rx="4">'
            f"<title>{esc(label)}: {_format_int(value)} {esc(unit)}</title></rect>"
        )
        parts.append(
            f'<text x="{width}" y="{y + 14}" text-anchor="end" class="bar-value">{_format_int(value)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def donut(
    items: Sequence[tuple[str, float, str]],
    *,
    size: int = 210,
    center_label: str = "",
    center_value: str = "",
    aria_label: str = "Donut chart",
) -> str:
    total = sum(value for _, value, _ in items)
    if not items or total <= 0:
        return '<p class="empty">No data</p>'

    radius = size / 2 - 18
    circumference = 2 * math.pi * radius
    offset = 0.0

    parts = [
        f'<svg class="chart donut" viewBox="0 0 {size} {size}" role="img" aria-label="{esc(aria_label)}">',
        f'<g transform="rotate(-90 {size / 2} {size / 2})">',
        f'<circle cx="{size / 2}" cy="{size / 2}" r="{radius}" fill="none" stroke="var(--grid)" stroke-width="18"/>',
    ]
    for label, value, color in items:
        length = circumference * float(value) / total
        dash = max(length - 2.5, 0.1)
        parts.append(
            f'<circle cx="{size / 2}" cy="{size / 2}" r="{radius}" fill="none" stroke="{color}" '
            f'stroke-width="18" stroke-dasharray="{dash:.2f} {circumference:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}" stroke-linecap="butt">'
            f"<title>{esc(label)}: {_format_int(value)}</title></circle>"
        )
        offset += length
    parts.append("</g>")
    parts.append(
        f'<text x="{size / 2}" y="{size / 2 - 2}" text-anchor="middle" class="donut-value">{esc(center_value)}</text>'
    )
    parts.append(
        f'<text x="{size / 2}" y="{size / 2 + 18}" text-anchor="middle" class="donut-label">{esc(center_label)}</text>'
    )
    parts.append("</svg>")

    legend = ['<ul class="legend">']
    for label, value, color in items:
        share = 100 * float(value) / total
        legend.append(
            f'<li><span class="dot" style="background:{esc(color)}"></span>'
            f'<span class="legend-label">{esc(label)}</span>'
            f'<span class="legend-value">{_format_int(value)}</span>'
            f'<span class="legend-share">{share:.0f}%</span></li>'
        )
    legend.append("</ul>")
    return "".join(parts) + "".join(legend)


def sparkline(values: Sequence[float], *, width: int = 120, height: int = 32, color: str = "#f59e0b") -> str:
    if not values:
        return ""
    maximum = max(values) or 1
    step = width / max(len(values) - 1, 1)
    points = " ".join(
        f"{idx * step:.1f},{height - (float(value) / maximum) * (height - 4) - 2:.1f}"
        for idx, value in enumerate(values)
    )
    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" aria-hidden="true">'
        f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="1.6"/></svg>'
    )


def merge_ranges(ranges: Iterable[tuple[dt.date, dt.date]]) -> list[tuple[dt.date, dt.date]]:
    """Handy for tests/docs: merge overlapping ingest windows before querying."""
    ordered = sorted(ranges)
    merged: list[tuple[dt.date, dt.date]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1] + dt.timedelta(days=1):
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged
