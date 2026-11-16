from __future__ import annotations

import datetime as dt

import pytest

from pipeline.charts import merge_ranges
from pipeline.util import date_windows, haversine_km


class TestDateWindows:
    def test_splits_inclusively_without_gaps(self):
        windows = date_windows(dt.date(2026, 1, 1), dt.date(2026, 3, 15), max_days=31)
        assert windows[0] == (dt.date(2026, 1, 1), dt.date(2026, 1, 31))
        assert windows[-1][1] == dt.date(2026, 3, 15)
        for previous, current in zip(windows, windows[1:], strict=False):
            assert current[0] == previous[1] + dt.timedelta(days=1)

    def test_single_day(self):
        assert date_windows(dt.date(2026, 5, 5), dt.date(2026, 5, 5)) == [
            (dt.date(2026, 5, 5), dt.date(2026, 5, 5))
        ]

    def test_rejects_reversed_range(self):
        with pytest.raises(ValueError):
            date_windows(dt.date(2026, 2, 1), dt.date(2026, 1, 1))


class TestHaversine:
    def test_jakarta_to_bandung(self):
        distance = haversine_km(-6.2088, 106.8456, -6.9175, 107.6191)
        assert 110 < distance < 130

    def test_zero_distance(self):
        assert haversine_km(1.0, 2.0, 1.0, 2.0) == pytest.approx(0.0, abs=1e-9)


class TestMergeRanges:
    def test_merges_overlapping_windows(self):
        merged = merge_ranges(
            [
                (dt.date(2026, 1, 1), dt.date(2026, 1, 31)),
                (dt.date(2026, 2, 1), dt.date(2026, 2, 10)),
                (dt.date(2026, 3, 1), dt.date(2026, 3, 5)),
            ]
        )
        assert merged == [
            (dt.date(2026, 1, 1), dt.date(2026, 2, 10)),
            (dt.date(2026, 3, 1), dt.date(2026, 3, 5)),
        ]
