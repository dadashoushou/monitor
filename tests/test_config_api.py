import app as app_module
from pathlib import Path
import json


def test_update_config_rejects_interval_outside_1_to_12(monkeypatch):
    current_cfg = {"crawl_interval_hours": 1}

    def fake_load_config():
        return current_cfg.copy()

    def fake_save_config(cfg):
        current_cfg.update(cfg)

    monkeypatch.setattr(app_module, "load_config", fake_load_config)
    monkeypatch.setattr(app_module, "save_config", fake_save_config)
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        low = client.post("/api/config", json={"crawl_interval_hours": 0})
        high = client.post("/api/config", json={"crawl_interval_hours": 13})
        ok = client.post("/api/config", json={"crawl_interval_hours": 12})

    assert low.status_code == 400
    assert high.status_code == 400
    assert ok.status_code == 200
    assert ok.get_json()["crawl_interval_hours"] == 12


def test_data_dir_check_accepts_writable_directory(tmp_path):
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        response = client.post(
            "/api/config/data-dir-check",
            json={"data_dir": str(tmp_path / "json-output")},
        )

    assert response.status_code == 200
    assert response.get_json()["valid"] is True
    assert Path(response.get_json()["data_dir"]).is_dir()


def test_data_dir_check_rejects_unwritable_path(monkeypatch, tmp_path):
    app_module.app.config["TESTING"] = True

    def fail_validate(raw):
        return False, Path(raw), "路径无效或无写入权限"

    monkeypatch.setattr(app_module, "validate_data_dir", fail_validate)

    with app_module.app.test_client() as client:
        response = client.post(
            "/api/config/data-dir-check",
            json={"data_dir": str(tmp_path / "blocked")},
        )

    assert response.status_code == 400
    assert response.get_json()["valid"] is False


def test_start_service_rejects_invalid_configured_data_dir(monkeypatch):
    app_module.app.config["TESTING"] = True
    monkeypatch.setattr(
        app_module,
        "load_config",
        lambda: {"data_dir": "Z:\\generate", "scheduler_on": False},
    )
    monkeypatch.setattr(
        app_module,
        "validate_data_dir",
        lambda raw: (False, Path(raw), "路径无效或无写入权限"),
    )

    with app_module.app.test_client() as client:
        response = client.post(
            "/api/system/crawl-service",
            json={"enabled": True},
        )

    assert response.status_code == 400
    assert "JSON 输出路径" in response.get_json()["error"]


def test_save_config_replaces_config_atomically(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(app_module, "CONFIG_FILE", config_file)

    app_module.save_config({"data_dir": str(tmp_path / "output")})

    assert json.loads(config_file.read_text(encoding="utf-8"))["data_dir"].endswith(
        "output"
    )
    assert list(tmp_path.glob("*.tmp")) == []


def test_add_site_accepts_content_selector_and_article_crawl_mode(monkeypatch):
    sites = []

    def fake_save_sites(updated):
        sites[:] = updated

    monkeypatch.setattr(app_module, "load_sites", lambda: sites)
    monkeypatch.setattr(app_module, "save_sites", fake_save_sites)
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        response = client.post(
            "/api/sites",
            json={
                "name": "Two-stage",
                "url": "example.com",
                "selectors": {"css_selector": "a.news"},
                "content_selector": "article .body",
                "article_crawl_mode": "stealth",
                "content_selector_generated_by": "manual",
                "content_selector_generated_at": "2026-09-13T08:00:00",
            },
        )

    assert response.status_code == 201
    site = response.get_json()
    assert site["selectors"]["css_selector"] == "a.news"
    assert site["content_selector"] == "article .body"
    assert site["article_crawl_mode"] == "stealth"
    assert site["content_selector_generated_by"] == "manual"
    assert site["content_selector_generated_at"] == "2026-09-13T08:00:00"


def test_update_site_accepts_and_clears_content_rule(monkeypatch):
    sites = [{
        "id": "site-1",
        "name": "Example",
        "url": "https://example.com",
        "article_crawl_mode": "auto",
        "content_selector": "article",
    }]
    monkeypatch.setattr(app_module, "load_sites", lambda: sites)
    monkeypatch.setattr(app_module, "save_sites", lambda updated: None)
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        response = client.put(
            "/api/sites/site-1",
            json={"content_selector": "  div.article-body  ", "article_crawl_mode": "js"},
        )
        cleared = client.put(
            "/api/sites/site-1",
            json={"content_selector": "", "article_crawl_mode": "invalid"},
        )

    assert response.status_code == 200
    assert response.get_json()["content_selector"] == "div.article-body"
    assert response.get_json()["article_crawl_mode"] == "js"
    assert cleared.status_code == 200
    assert cleared.get_json()["content_selector"] is None
    assert cleared.get_json()["article_crawl_mode"] == "js"


def test_site_api_normalizes_content_selector_arrays(monkeypatch):
    sites = []
    monkeypatch.setattr(app_module, "load_sites", lambda: sites)
    monkeypatch.setattr(app_module, "save_sites", lambda updated: sites.__setitem__(slice(None), updated))
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        response = client.post(
            "/api/sites",
            json={
                "name": "Array selectors",
                "url": "https://example.com",
                "content_selector": [" article ", "", "div.article-body", 3],
            },
        )

    assert response.status_code == 201
    assert response.get_json()["content_selector"] == [
        "article",
        "div.article-body",
    ]


def test_old_site_config_gets_compatible_defaults(monkeypatch, tmp_path):
    fixture = tmp_path / "old-sites.json"
    monkeypatch.setattr(app_module, "DATA_FILE", fixture)
    fixture.write_text(
        json.dumps([{"id": "old", "name": "Old", "url": "https://old.example"}]),
        encoding="utf-8",
    )

    sites = app_module.load_sites()

    assert sites[0]["content_selector"] is None
    assert sites[0]["article_crawl_mode"] == "auto"


def test_rule_preview_endpoint_returns_content_hit_and_mode(monkeypatch):
    site = {
        "id": "site-1",
        "name": "Preview",
        "url": "https://example.com",
        "crawl_mode": "html",
        "article_crawl_mode": "stealth",
        "content_selector": "article .body",
    }
    monkeypatch.setattr(app_module, "load_sites", lambda: [site])
    monkeypatch.setattr(
        app_module,
        "_preview_site_rules",
        lambda preview_site, limit: {
            "site_id": preview_site["id"],
            "article_crawl_mode": preview_site["article_crawl_mode"],
            "content_selector": preview_site["content_selector"],
            "count": limit,
            "items": [{
                "content_length": 123,
                "content_hit": True,
                "content_selector_hit": True,
                "article_crawl_mode": "stealth",
            }],
        },
    )
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        response = client.post(
            "/api/sites/site-1/rule-preview",
            json={"limit": 1},
        )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["article_crawl_mode"] == "stealth"
    assert payload["items"][0]["content_length"] == 123
    assert payload["items"][0]["content_hit"] is True
    assert payload["items"][0]["content_selector_hit"] is True


def test_translate_result_keeps_original_text_and_adds_chinese(monkeypatch):
    result = {
        "site_id": "site-1",
        "items": [{
            "title": "English title",
            "content": "English content",
        }],
    }
    cfg = {
        "translation": {
            "enabled": True,
            "engine": "google",
            "from_language": "en",
            "to_language": "zh",
            "max_chunk_chars": 4000,
        }
    }
    translations = {
        "English title": "中文标题",
        "English content": "中文正文",
    }
    monkeypatch.setattr(
        app_module,
        "_translate_text",
        lambda text, _cfg: translations[text],
    )

    translated = app_module._translate_result(result, cfg)
    item = translated["items"][0]

    assert item["title"] == "English title"
    assert item["content"] == "English content"
    assert item["title_zh"] == "中文标题"
    assert item["content_zh"] == "中文正文"
    assert item["translation"]["provider"] == "translators"
    assert item["translation"]["status"] == "success"


def test_translate_result_leaves_chinese_empty_on_failure(monkeypatch):
    result = {
        "site_id": "site-1",
        "items": [{
            "title": "English title",
            "content": "English content",
        }],
    }
    cfg = {"translation": {"enabled": True}}

    def fail_translate(_text, _cfg):
        raise RuntimeError("translation unavailable")

    monkeypatch.setattr(app_module, "_translate_text", fail_translate)

    translated = app_module._translate_result(result, cfg)
    item = translated["items"][0]

    assert item["title"] == "English title"
    assert item["content"] == "English content"
    assert item["title_zh"] == ""
    assert item["content_zh"] == ""
    assert item["translation"]["status"] == "failed"
    assert "translation unavailable" in item["translation"]["error"]
