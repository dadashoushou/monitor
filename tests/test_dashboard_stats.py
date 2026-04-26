import json
from datetime import datetime as real_datetime

import app as app_module


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


class _FakeDateTime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 4, 26, 12, 0, 0, tzinfo=tz)


def test_system_stats_roll_up_day_week_and_month_from_snapshot_filenames(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    _write_json(
        data_dir / "2026-04-26_08-00-00_site-1.json",
        {"count": 2, "items": [{"title": "a"}, {"title": "b"}]},
    )
    _write_json(
        data_dir / "2026-04-24_09-00-00_site-2.json",
        {"count": 3, "items": [{"title": "c"}]},
    )
    _write_json(
        data_dir / "2026-04-21_10-30-00_site-3.json",
        {"items": [{"title": "d"}, {"title": "e"}, {"title": "f"}, {"title": "g"}]},
    )
    _write_json(
        data_dir / "2026-04-05_11-00-00_site-4.json",
        {"count": 5, "items": []},
    )
    _write_json(
        data_dir / "2026-03-30_11-00-00_site-5.json",
        {"count": 7, "items": []},
    )
    _write_json(data_dir / "invalid_name.json", {"count": 100, "items": []})

    monkeypatch.setattr(app_module, "get_data_dir", lambda: data_dir)
    monkeypatch.setattr(app_module, "datetime", _FakeDateTime)
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        resp = client.get("/api/system/stats")

    assert resp.status_code == 200
    assert resp.get_json() == {
        "month_count": 14,
        "week_count": 9,
        "day_count": 2,
    }
