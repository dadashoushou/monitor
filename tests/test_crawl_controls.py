import app as app_module


def test_toggle_site_crawl_updates_pause_flag(monkeypatch):
    sites = [
        {
            "id": "site-1",
            "name": "Example",
            "url": "https://example.com",
            "crawl_paused": False,
        }
    ]

    def fake_load_sites():
        return sites

    def fake_save_sites(updated):
        sites[:] = updated

    monkeypatch.setattr(app_module, "load_sites", fake_load_sites)
    monkeypatch.setattr(app_module, "save_sites", fake_save_sites)
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        resp = client.post("/api/sites/site-1/crawl-toggle", json={"paused": True})

    assert resp.status_code == 200
    assert resp.get_json()["crawl_paused"] is True
    assert sites[0]["crawl_paused"] is True


def test_crawl_one_route_rejects_paused_site(monkeypatch):
    sites = [
        {
            "id": "site-1",
            "name": "Example",
            "url": "https://example.com",
            "crawl_paused": True,
        }
    ]

    monkeypatch.setattr(app_module, "load_sites", lambda: sites)
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        resp = client.post("/api/crawl/site-1")

    assert resp.status_code == 409
    assert resp.get_json()["error"] == "site crawl paused"


def test_output_site_test_writes_report_without_saving_crawl_result(monkeypatch, tmp_path):
    site = {
        "id": "site-1",
        "name": "Example / Site",
        "url": "https://example.com",
        "crawl_mode": "html",
        "article_crawl_mode": "stealth",
        "content_selector": ["article", "div.body"],
    }
    report_path = tmp_path / "Example _ Site.txt"
    monkeypatch.setattr(app_module, "load_sites", lambda: [site])
    monkeypatch.setattr(app_module, "load_config", lambda: {"translation": {"enabled": False}})
    monkeypatch.setattr(app_module, "_test_report_path", lambda name: report_path)
    monkeypatch.setattr(
        app_module,
        "_crawl_site",
        lambda tested_site: {
            "method": "html",
            "count": 1,
            "items": [{
                "title": "Test article",
                "url": "https://example.com/article",
                "published": None,
                "content": "正文内容",
            }],
        },
    )
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        response = client.post("/api/sites/site-1/output-test")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 1
    assert payload["content_count"] == 1
    assert report_path.exists()
    report = report_path.read_text(encoding="utf-8")
    assert "Test article" in report
    assert "正文内容" in report


def test_output_site_test_uses_translation_channel(monkeypatch, tmp_path):
    site = {
        "id": "site-1",
        "name": "Example",
        "url": "https://example.com",
    }
    report_path = tmp_path / "Example.txt"
    translated = []

    monkeypatch.setattr(app_module, "load_sites", lambda: [site])
    monkeypatch.setattr(app_module, "_test_report_path", lambda name: report_path)
    monkeypatch.setattr(
        app_module,
        "_crawl_site",
        lambda tested_site: {
            "count": 1,
            "items": [{
                "title": "English title",
                "content": "English content",
            }],
        },
    )
    monkeypatch.setattr(
        app_module,
        "load_config",
        lambda: {"translation": {"enabled": True}},
    )

    def fake_translate(result, cfg):
        translated.append((result, cfg))
        result["items"][0]["title_zh"] = "中文标题"
        result["items"][0]["content_zh"] = "中文正文"
        result["items"][0]["translation"] = {"status": "success"}
        return result

    monkeypatch.setattr(app_module, "_translate_result", fake_translate)
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        response = client.post("/api/sites/site-1/output-test")

    assert response.status_code == 200
    assert len(translated) == 1
    assert translated[0][1]["translation"]["enabled"] is True
    report = report_path.read_text(encoding="utf-8")
    assert "中文标题" in report
    assert "中文正文" in report


def test_crawl_logs_api_returns_local_history_newest_first(monkeypatch, tmp_path):
    log_file = tmp_path / "crawl_logs.jsonl"
    monkeypatch.setattr(app_module, "CRAWL_LOG_FILE", log_file)
    app_module._append_crawl_log({
        "source": "全部抓取",
        "finished_at": "2026-09-16 10:00:00",
        "sites": [],
    })
    app_module._append_crawl_log({
        "source": "单站抓取",
        "finished_at": "2026-09-16 11:00:00",
        "sites": [],
    })
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        response = client.get("/api/crawl/logs")

    assert response.status_code == 200
    payload = response.get_json()
    assert [item["source"] for item in payload["logs"]] == ["单站抓取", "全部抓取"]
    assert log_file.exists()


def test_crawl_one_route_writes_title_only_failure_log(monkeypatch, tmp_path):
    site = {
        "id": "site-1",
        "name": "Example",
        "url": "https://example.com",
    }
    log_file = tmp_path / "crawl_logs.jsonl"
    monkeypatch.setattr(app_module, "CRAWL_LOG_FILE", log_file)
    monkeypatch.setattr(app_module, "load_sites", lambda: [site])
    monkeypatch.setattr(app_module, "load_config", lambda: {"site_timeout_seconds": 300})
    monkeypatch.setattr(app_module, "_known_urls_for_site", lambda site_id: set())
    monkeypatch.setattr(app_module, "_dedupe_items_with_mirror", lambda site_id, items: items)
    monkeypatch.setattr(app_module, "_save_single_result", lambda site_id, result: result)
    monkeypatch.setattr(
        app_module,
        "_crawl_site",
        lambda tested_site: {
            "site_id": "site-1",
            "site_name": "Example",
            "site_url": "https://example.com",
            "method": "html",
            "count": 1,
            "items": [{
                "title": "Title only",
                "url": "https://example.com/a",
                "content": "",
            }],
        },
    )
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        response = client.post("/api/crawl/site-1")

    assert response.status_code == 200
    logs = app_module._read_crawl_logs()
    assert logs[-1]["source"] == "单站抓取"
    assert logs[-1]["failed_count"] == 1
    assert logs[-1]["sites"][0]["reason"] == "只抓取到标题，未抓到原文"


def test_site_result_log_explains_article_http_failure():
    site = {
        "id": "site-1",
        "name": "Example",
        "url": "https://example.com",
    }
    result = {
        "method": "html",
        "count": 1,
        "items": [{"title": "Title only", "content": ""}],
        "article_errors": [{
            "url": "https://example.com/article",
            "error": "详情页返回 HTTP 403",
            "http_status": 403,
        }],
    }

    log = app_module._site_result_log(site, result)

    assert log["status"] == "failed"
    assert log["reason"] == "只抓取到标题，未抓到原文：详情页返回 HTTP 403"


def test_site_result_log_marks_history_filtered_items_as_no_new():
    site = {
        "id": "site-1",
        "name": "Example",
        "url": "https://example.com",
    }
    result = {
        "method": "html",
        "count": 0,
        "items": [],
        "raw_article_count": 3,
        "history_filtered_count": 3,
        "new_article_count": 0,
        "no_new_items": True,
    }

    log = app_module._site_result_log(site, result)

    assert log["status"] == "skipped"
    assert log["reason"] == "本次抓到的文章均已存在历史记录"
    assert log["raw_article_count"] == 3
    assert log["history_filtered_count"] == 3
    assert log["new_article_count"] == 0


def test_site_result_log_marks_age_filtered_items_as_no_recent():
    site = {
        "id": "site-1",
        "name": "Example",
        "url": "https://example.com",
    }
    result = {
        "method": "rss",
        "count": 0,
        "items": [],
        "raw_article_count": 10,
        "eligible_article_count": 0,
        "age_filtered_count": 10,
        "history_filtered_count": 0,
        "new_article_count": 0,
        "no_recent_items": True,
    }

    log = app_module._site_result_log(site, result)

    assert log["status"] == "skipped"
    assert log["reason"] == "站点访问正常，但没有符合时效范围的文章"
    assert log["raw_article_count"] == 10
    assert log["age_filtered_count"] == 10


def test_site_result_log_keeps_http_failure_diagnostics():
    site = {
        "id": "site-1",
        "name": "Example",
        "url": "https://example.com",
    }
    result = {
        "method": "rss",
        "count": 0,
        "items": [],
        "error": "RSS 请求失败：HTTP 403",
        "error_stage": "rss_fetch",
        "http_status": 403,
        "error_url": "https://example.com/feed/",
    }

    log = app_module._site_result_log(site, result)

    assert log["status"] == "failed"
    assert log["http_status"] == 403
    assert log["error_stage"] == "rss_fetch"
    assert log["error_url"] == "https://example.com/feed/"


def test_crawl_run_log_summarizes_new_filtered_and_content_counts():
    run = app_module._crawl_run_log(
        "全部抓取",
        "2026-09-16 16:05:04",
        [
            {
                "status": "success",
                "article_count": 2,
                "new_article_count": 2,
                "history_filtered_count": 0,
                "content_count": 2,
            },
            {
                "status": "skipped",
                "article_count": 0,
                "new_article_count": 0,
                "history_filtered_count": 3,
                "content_count": 0,
            },
        ],
    )

    assert run["new_article_count"] == 2
    assert run["history_filtered_count"] == 3
    assert run["content_count"] == 2


def test_system_status_reports_scheduler_and_crawl_state(monkeypatch):
    cfg = {"crawl_interval_hours": 3, "scheduler_on": False}
    original_state = dict(app_module.crawl_state)

    monkeypatch.setattr(app_module, "load_config", lambda: cfg.copy())
    app_module.crawl_state.update({"last_run": "2026-04-25T12:00:00", "running": True, "stopped": True})
    app_module.app.config["TESTING"] = True

    try:
        with app_module.app.test_client() as client:
            resp = client.get("/api/system/status")
    finally:
        app_module.crawl_state.clear()
        app_module.crawl_state.update(original_state)

    assert resp.status_code == 200
    assert resp.get_json() == {
        "scheduler_on": False,
        "interval_hours": 3,
        "last_run": "2026-04-25T12:00:00",
        "crawl_running": True,
        "crawl_stopped": True,
    }
