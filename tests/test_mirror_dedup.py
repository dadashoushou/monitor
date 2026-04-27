import json

import app as app_module
from mirror_store import update_site_index


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def test_dedupe_ignores_legacy_data_dir_and_uses_mirror_titles_only(tmp_path, monkeypatch):
    legacy_dir = tmp_path / "legacy-data"
    mirror_dir = tmp_path / "history_mirror"
    site_id = "site-1"

    _write_json(
        legacy_dir / "2026-04-20_10-00-00_site-1.json",
        {
            "crawled_at": "2026-04-20T10:00:00",
            "site_id": site_id,
            "items": [{"title": "Legacy Title", "url": "https://example.com/legacy"}],
        },
    )

    monkeypatch.setattr(app_module, "get_data_dir", lambda: legacy_dir)
    monkeypatch.setattr(app_module, "get_mirror_data_dir", lambda: mirror_dir)
    app_module._reset_mirror_bootstrap()

    filtered = app_module._dedupe_items_with_mirror(
        site_id,
        [{"title": "Legacy Title", "url": "https://example.com/new"}],
    )

    assert len(filtered) == 1
    assert filtered[0]["title"] == "Legacy Title"
    assert list(mirror_dir.glob("*.json")) == []


def test_dedupe_uses_normalized_titles_within_site(tmp_path, monkeypatch):
    mirror_dir = tmp_path / "history_mirror"
    site_id = "site-2"
    update_site_index(
        mirror_dir,
        site_id,
        [{"title": "Repeated  Headline", "url": "https://example.com/first"}],
        updated_at="2026-04-20T09:10:00",
        site_url="https://example.com",
    )

    monkeypatch.setattr(app_module, "get_mirror_data_dir", lambda: mirror_dir)
    app_module._reset_mirror_bootstrap()

    filtered = app_module._dedupe_items_with_mirror(
        site_id,
        [
            {"title": "Repeated Headline", "url": "https://example.com/second"},
            {"title": "Fresh Headline", "url": "https://example.com/third"},
        ],
    )

    assert [item["title"] for item in filtered] == ["Fresh Headline"]


def test_crawl_one_route_dedupes_against_mirror_and_updates_title_index(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    mirror_dir = tmp_path / "history_mirror"
    site_id = "site-3"

    update_site_index(
        mirror_dir,
        site_id,
        [{"title": "Existing Title", "url": "https://example.com/old"}],
        updated_at="2026-04-20T08:00:00",
        site_url="https://example.com",
    )

    monkeypatch.setattr(app_module, "get_data_dir", lambda: data_dir)
    monkeypatch.setattr(app_module, "get_mirror_data_dir", lambda: mirror_dir)
    monkeypatch.setattr(
        app_module,
        "load_sites",
        lambda: [
            {
                "id": site_id,
                "name": "Site Three",
                "url": "https://example.com",
                "status": "rss",
                "rss_url": "https://example.com/feed",
            }
        ],
    )
    monkeypatch.setattr(
        app_module,
        "_crawl_site",
        lambda site: {
            "site_id": site["id"],
            "site_name": site["name"],
            "site_url": site["url"],
            "method": "rss",
            "count": 2,
            "items": [
                {
                    "title": "Existing Title",
                    "url": "https://example.com/article-1",
                    "published": "2026-04-20T11:00:00",
                    "crawled_at": "2026-04-21T09:00:00",
                },
                {
                    "title": "New Title",
                    "url": "https://example.com/article-2",
                    "published": "2026-04-21T11:00:00",
                    "crawled_at": "2026-04-21T09:00:00",
                },
            ],
        },
    )
    app_module._reset_mirror_bootstrap()
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        response = client.post(f"/api/crawl/{site_id}")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 1
    assert [item["title"] for item in payload["items"]] == ["New Title"]

    written_results = list(data_dir.glob(f"*_{site_id}.json"))
    assert len(written_results) == 1
    mirror_snapshots = list((mirror_dir / "snapshots").glob(f"*_{site_id}.json"))
    assert len(mirror_snapshots) == 1

    with open(mirror_dir / f"{site_id}.json", "r", encoding="utf-8") as f:
        index_payload = json.load(f)
    assert index_payload["site_id"] == site_id
    assert index_payload["site_url"] == "https://example.com"
    assert index_payload["updated_at"]
    assert index_payload["titles"] == ["Existing Title", "New Title"]
