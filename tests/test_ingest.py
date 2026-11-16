from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from pipeline import ingest as ingest_module


def _feature(event_id: str, mag: float, updated: int, hour: int = 0) -> dict:
    timestamp = int(dt.datetime(2026, 1, 1, hour, tzinfo=dt.timezone.utc).timestamp() * 1000)
    return {
        "type": "Feature",
        "id": event_id,
        "properties": {
            "mag": mag,
            "place": f"{event_id} place",
            "time": timestamp,
            "updated": updated,
            "tsunami": 0,
            "felt": None,
            "sig": 100,
            "status": "reviewed",
            "magType": "mww",
            "net": "us",
            "url": f"https://example.test/{event_id}",
        },
        "geometry": {"type": "Point", "coordinates": [120.0, -8.0, 10.0]},
    }


def _payload(features: list[dict]) -> dict:
    return {
        "type": "FeatureCollection",
        "metadata": {"status": 200, "count": len(features), "url": "https://example.test"},
        "features": features,
    }


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, payloads: list[dict]):
        self.payloads = payloads
        self.calls: list[dict] = []

    def get(self, url, params, timeout, headers):  # noqa: ANN001 - mirrors requests
        self.calls.append(params)
        return FakeResponse(self.payloads[len(self.calls) - 1])


class TestMergeFeatures:
    def test_keeps_newer_revision(self):
        old = _feature("a", 4.0, updated=100)
        new = _feature("a", 4.6, updated=200)
        merged = ingest_module.merge_features([old], [new])
        assert len(merged) == 1
        assert merged[0]["properties"]["mag"] == 4.6

    def test_ignores_older_revision(self):
        old = _feature("a", 4.0, updated=100)
        stale = _feature("a", 4.6, updated=50)
        merged = ingest_module.merge_features([old], [stale])
        assert merged[0]["properties"]["mag"] == 4.0

    def test_sorted_by_origin_time(self):
        late = _feature("late", 4.0, updated=1, hour=5)
        early = _feature("early", 4.0, updated=1, hour=1)
        merged = ingest_module.merge_features([late], [early])
        assert [feature["id"] for feature in merged] == ["early", "late"]


class TestWritePartition:
    def test_same_day_rerun_merges_and_overwrites(self, tmp_path):
        day = dt.date(2026, 1, 2)
        ingest_module.write_partition([_feature("a", 4.0, 100)], day, data_dir=tmp_path)
        target = ingest_module.write_partition([_feature("a", 4.8, 200), _feature("b", 3.2, 1)], day, data_dir=tmp_path)
        document = json.loads(target.read_text())
        assert document["metadata"]["count"] == 2
        assert target == tmp_path / "usgs" / "dt=2026-01-02" / "events.json"

    def test_recovers_from_corrupt_partition(self, tmp_path):
        day = dt.date(2026, 1, 3)
        target = ingest_module.bronze_path(tmp_path, day)
        target.parent.mkdir(parents=True)
        target.write_text("{not json")
        result = ingest_module.write_partition([_feature("c", 3.0, 1)], day, data_dir=tmp_path)
        assert json.loads(result.read_text())["metadata"]["count"] == 1


class TestIngest:
    def test_two_windows_written_and_logged(self, tmp_path):
        session = FakeSession(
            [
                _payload([_feature("a", 4.0, 1)]),
                _payload([_feature("b", 3.5, 1)]),
            ]
        )
        result = ingest_module.ingest(
            dt.date(2026, 1, 1),
            dt.date(2026, 2, 15),
            data_dir=tmp_path,
            session=session,
            run_day=dt.date(2026, 2, 15),
            record=False,
        )
        assert result.status == "success"
        assert result.windows == 2
        assert result.events_fetched == 2
        assert len(session.calls) == 2
        document = json.loads(Path(result.files_written[0]).read_text())
        assert document["metadata"]["count"] == 2
        assert result.duration_seconds is not None

    def test_window_params_respect_bbox_and_magnitude(self, tmp_path):
        session = FakeSession([_payload([])])
        ingest_module.ingest(
            dt.date(2026, 4, 1),
            dt.date(2026, 4, 1),
            data_dir=tmp_path,
            session=session,
            run_day=dt.date(2026, 4, 1),
            record=False,
        )
        params = session.calls[0]
        assert params["minmagnitude"] == "2.5"
        assert params["minlatitude"] == "-12.0"
        assert params["format"] == "geojson"
