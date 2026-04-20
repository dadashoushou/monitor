from datetime import datetime as real_datetime
import re

import pytest

import app as app_module


@pytest.fixture()
def client(monkeypatch):
    config_state = {
        "data_dir": "",
        "scan_interval_minutes": 5,
        "port": 5001,
    }

    def fake_load_config():
        return dict(config_state)

    def fake_save_config(cfg):
        config_state.clear()
        config_state.update(cfg)

    monkeypatch.setattr(app_module, "load_config", fake_load_config)
    monkeypatch.setattr(app_module, "save_config", fake_save_config)
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as test_client:
        yield test_client


def test_update_config_rejects_scan_interval_below_five(client):
    response = client.post(
        "/api/config",
        json={
            "data_dir": str(app_module.BASE_DIR),
            "scan_interval_minutes": 4,
        },
    )

    assert response.status_code == 400
    assert "5" in response.get_json()["error"]


def test_update_config_refreshes_scheduler_job_interval(client, monkeypatch):
    calls = []

    def fake_refresh(minutes):
        calls.append(minutes)

    monkeypatch.setattr(app_module, "refresh_scan_schedule", fake_refresh, raising=False)

    response = client.post(
        "/api/config",
        json={
            "data_dir": str(app_module.BASE_DIR),
            "scan_interval_minutes": 15,
        },
    )

    assert response.status_code == 200
    assert response.get_json()["scan_interval_minutes"] == 15
    assert calls == [15]


def test_homepage_contains_readable_scan_labels(client):
    page = client.get("/").get_data(as_text=True)

    assert "扫描目录" in page
    assert "间隔(分钟)" in page
    assert ">保存</button>" in page


def test_homepage_reuses_translation_rendering_for_trash_titles(client):
    page = client.get("/").get_data(as_text=True)
    load_trash_match = re.search(r"async function loadTrash\(page\) \{.*?\n\}", page, re.S)
    render_trash_match = re.search(r"function renderTrash\(items, total\) \{.*?\n\}", page, re.S)

    assert load_trash_match
    assert render_trash_match
    assert "await loadTranslationsForItems(d.items);" in load_trash_match.group(0)
    assert "const zh = getTitleZh(a);" in render_trash_match.group(0)
    assert "toggleEnglish(${a.seq})" in render_trash_match.group(0)
    assert 'class="english-row" id="en-${a.seq}"' in render_trash_match.group(0)


def test_homepage_renders_source_domain_helpers_for_expanded_english_titles(client):
    page = client.get("/").get_data(as_text=True)
    source_host_match = re.search(r"function getSourceHost\(url\) \{.*?\n\}", page, re.S)
    source_meta_match = re.search(r"function renderEnglishSourceMeta\(article\) \{.*?\n\}", page, re.S)
    render_articles_match = re.search(r"function renderArticles\(items, total\) \{.*?\n\}", page, re.S)
    render_trash_match = re.search(r"function renderTrash\(items, total\) \{.*?\n\}", page, re.S)

    assert source_host_match
    assert source_meta_match
    assert render_articles_match
    assert render_trash_match
    assert "new URL(url)" in source_host_match.group(0)
    assert "const label = getSourceHost(article.source_url) || article.source_site || '';" in source_meta_match.group(0)
    assert 'class="english-source-link"' in source_meta_match.group(0)
    assert 'title="${esc(article.source_url)}"' in source_meta_match.group(0)
    assert "const sourceMeta = renderEnglishSourceMeta(a);" in render_articles_match.group(0)
    assert "const sourceMeta = renderEnglishSourceMeta(a);" in render_trash_match.group(0)


def test_homepage_renders_visible_source_url_text_in_expanded_english_rows(client):
    page = client.get("/").get_data(as_text=True)
    source_meta_match = re.search(r"function renderEnglishSourceMeta\(article\) \{.*?\n\}", page, re.S)

    assert source_meta_match
    assert 'class="english-source-label"' in source_meta_match.group(0)
    assert 'class="english-source-value"' in source_meta_match.group(0)
    assert '${esc(article.source_url)}' in source_meta_match.group(0)


def test_homepage_keeps_source_close_to_english_title(client):
    page = client.get("/").get_data(as_text=True)
    css_match = re.search(r"\.english-row-content \{.*?\}\n\.english-row-title \{.*?\}", page, re.S)

    assert css_match
    assert "justify-content: flex-start;" in css_match.group(0)
    assert "flex: 0 1 auto;" in css_match.group(0)


def test_homepage_uses_inline_top_config_without_legacy_modal(client):
    page = client.get("/").get_data(as_text=True)

    assert 'id="topDataDir"' in page
    assert 'id="topScanInterval"' in page
    assert "function saveTopConfig()" in page
    assert 'id="configModal"' not in page
    assert 'onclick="openConfig()"' not in page


def test_homepage_syncs_view_state_through_url(client):
    page = client.get("/").get_data(as_text=True)

    assert "function readViewStateFromUrl()" in page
    assert "function writeViewStateToUrl()" in page
    assert "new URLSearchParams(window.location.search)" in page
    assert "window.history.replaceState({}, '', nextUrl);" in page
    assert "window.addEventListener('popstate', () => {" in page


def test_homepage_requires_confirmation_for_single_delete_and_uses_explicit_title_toggle(client):
    page = client.get("/").get_data(as_text=True)
    delete_match = re.search(r"async function deleteArticle\(seq\) \{.*?\n\}", page, re.S)
    render_articles_match = re.search(r"function renderArticles\(items, total\) \{.*?\n\}", page, re.S)
    render_trash_match = re.search(r"function renderTrash\(items, total\) \{.*?\n\}", page, re.S)

    assert delete_match
    assert render_articles_match
    assert render_trash_match
    assert "confirm(" in delete_match.group(0)
    assert 'class="title-toggle"' in render_articles_match.group(0)
    assert 'class="title-toggle"' in render_trash_match.group(0)


def test_homepage_weakens_bulk_actions_until_items_are_selected(client):
    page = client.get("/").get_data(as_text=True)

    assert "function syncBulkActionState(view)" in page
    assert "syncBulkActionState('articles');" in page
    assert "syncBulkActionState('trash');" in page
    assert 'class="bulk-actions"' in page


class FixedDatetime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 4, 20, 9, 30, 0, tzinfo=tz)


def test_get_trash_defaults_to_today_scope(client, monkeypatch):
    monkeypatch.setattr(app_module, "datetime", FixedDatetime)
    monkeypatch.setattr(
        app_module,
        "load_state",
        lambda: {
            "articles": [
                {"seq": 1, "title": "today item", "deleted": True, "deleted_at": "2026-04-20T08:00:00"},
                {"seq": 2, "title": "yesterday item", "deleted": True, "deleted_at": "2026-04-19T08:00:00"},
                {"seq": 3, "title": "older item", "deleted": True, "deleted_at": "2026-04-18T08:00:00"},
            ]
        },
    )

    response = client.get("/api/trash")

    assert response.status_code == 200
    payload = response.get_json()
    assert [item["seq"] for item in payload["items"]] == [1]
    assert payload["total"] == 1


@pytest.mark.parametrize(
    ("scope", "expected_seqs"),
    [
        ("yesterday", [2]),
        ("earlier", [3, 4]),
    ],
)
def test_get_trash_filters_requested_time_scope(client, monkeypatch, scope, expected_seqs):
    monkeypatch.setattr(app_module, "datetime", FixedDatetime)
    monkeypatch.setattr(
        app_module,
        "load_state",
        lambda: {
            "articles": [
                {"seq": 1, "title": "today item", "deleted": True, "deleted_at": "2026-04-20T08:00:00"},
                {"seq": 2, "title": "yesterday item", "deleted": True, "deleted_at": "2026-04-19T08:00:00"},
                {"seq": 3, "title": "older item", "deleted": True, "deleted_at": "2026-04-18T08:00:00"},
                {"seq": 4, "title": "legacy item", "deleted": True, "deleted_at": None},
            ]
        },
    )

    response = client.get(f"/api/trash?scope={scope}")

    assert response.status_code == 200
    payload = response.get_json()
    assert [item["seq"] for item in payload["items"]] == expected_seqs
    assert payload["total"] == len(expected_seqs)


def test_get_trash_search_stays_within_selected_scope(client, monkeypatch):
    monkeypatch.setattr(app_module, "datetime", FixedDatetime)
    monkeypatch.setattr(
        app_module,
        "load_state",
        lambda: {
            "articles": [
                {"seq": 1, "title": "alpha today", "deleted": True, "deleted_at": "2026-04-20T08:00:00"},
                {"seq": 2, "title": "alpha yesterday", "deleted": True, "deleted_at": "2026-04-19T08:00:00"},
                {"seq": 3, "title": "beta older", "deleted": True, "deleted_at": "2026-04-18T08:00:00"},
            ]
        },
    )

    response = client.get("/api/trash?scope=today&q=alpha")

    assert response.status_code == 200
    payload = response.get_json()
    assert [item["seq"] for item in payload["items"]] == [1]
    assert payload["total"] == 1
