import json

import app as app_module


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_results_summary_returns_latest_result_per_site(tmp_path, monkeypatch):
    data_dir = tmp_path / "history_mirror" / "snapshots"
    _write_json(
        data_dir / "2026-09-12_10-00-00_site-1.json",
        {"site_id": "site-1", "count": 2, "method": "html", "crawled_at": "old"},
    )
    _write_json(
        data_dir / "2026-09-13_10-00-00_site-1.json",
        {"site_id": "site-1", "count": 5, "method": "rss", "crawled_at": "new"},
    )
    _write_json(
        data_dir / "2026-09-13_09-00-00_site-2.json",
        {"count": 3, "method": "html", "crawled_at": "site-2"},
    )
    monkeypatch.setattr(app_module, "get_mirror_snapshots_dir", lambda: data_dir)
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        response = client.get("/api/results/summary")

    assert response.status_code == 200
    assert response.get_json() == {
        "site-1": {
            "filename": "2026-09-13_10-00-00_site-1.json",
            "crawled_at": "new",
            "count": 5,
            "method": "rss",
        },
        "site-2": {
            "filename": "2026-09-13_09-00-00_site-2.json",
            "crawled_at": "site-2",
            "count": 3,
            "method": "html",
        },
    }
