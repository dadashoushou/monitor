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
