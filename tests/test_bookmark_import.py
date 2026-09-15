from pathlib import Path

import app as app_module


FIXTURE_PATH = Path(__file__).with_name("_bookmark_import_fixture.html")


def _write_fixture(content: str) -> Path:
    FIXTURE_PATH.write_text(content, encoding="utf-8")
    return FIXTURE_PATH


def _cleanup_fixture():
    if FIXTURE_PATH.exists():
        FIXTURE_PATH.unlink()


def test_import_bookmarks_creates_sites_from_html(monkeypatch):
    try:
        html_path = _write_fixture(
            """
            <DL><p>
              <DT><A HREF="https://example.com/a">Example A</A>
              <DT><A HREF="example.com/b">Example B</A>
              <DT><A HREF="https://example.com/a">Duplicate A</A>
              <DT><A HREF="javascript:void(0)">Skip</A>
            </DL>
            """
        )

        sites = []

        def fake_load_sites():
            return sites

        def fake_save_sites(updated):
            sites[:] = updated

        monkeypatch.setattr(app_module, "load_sites", fake_load_sites)
        monkeypatch.setattr(app_module, "save_sites", fake_save_sites)
        app_module.app.config["TESTING"] = True

        with app_module.app.test_client() as client:
            resp = client.post("/api/import/bookmarks", json={"path": str(html_path)})
    finally:
        _cleanup_fixture()

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["imported"] == 2
    assert payload["skipped"] == 0
    assert payload["total_found"] == 2
    assert [site["name"] for site in sites] == ["Example A", "Example B"]
    assert [site["seq"] for site in sites] == [1, 2]
    assert sites[0]["url"] == "https://example.com/a"
    assert sites[1]["url"] == "https://example.com/b"


def test_import_bookmarks_skips_existing_sites(monkeypatch):
    try:
        html_path = _write_fixture(
            """
            <DL><p>
              <DT><A HREF="https://example.com/a">Example A</A>
              <DT><A HREF="https://example.com/c">Example C</A>
            </DL>
            """
        )

        sites = [
            {
                "seq": 1,
                "id": "existing",
                "name": "Existing",
                "url": "https://example.com/a",
                "note": "",
                "rss_url": None,
                "status": "pending",
                "last_checked": None,
                "crawl_mode": "auto",
                "crawl_paused": False,
                "selectors": None,
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
            resp = client.post("/api/import/bookmarks", json={"path": str(html_path)})
    finally:
        _cleanup_fixture()

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["imported"] == 1
    assert payload["skipped"] == 1
    assert [site["url"] for site in sites] == ["https://example.com/a", "https://example.com/c"]
