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
