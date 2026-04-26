import app as app_module


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
