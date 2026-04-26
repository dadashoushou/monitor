import re

import app as app_module


def test_root_homepage_protects_modal_from_accidental_close_and_submit():
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        page = client.get("/").get_data(as_text=True)

    assert "function serializeModalForm()" in page
    assert "function hasUnsavedModalChanges()" in page
    assert "function confirmDiscardModalChanges()" in page
    assert 'id="overlay" onpointerdown="trackModalBackdropPointerDown(event)" onclick="closeModalOnBg(event)"' in page
    assert "let modalBackdropPointerDown = false;" in page
    assert "function trackModalBackdropPointerDown(e)" in page
    assert "function resetModalBackdropPointerState()" in page
    assert "const shouldClose = modalBackdropPointerDown && e.target === overlay && e.currentTarget === overlay;" in page
    assert 'id="overlay" onmousedown="closeModalOnBg(event)"' not in page
    assert "if (e.key === 'Enter' && document.getElementById('overlay').classList.contains('open')) saveSite();" not in page


def test_root_homepage_uses_history_drawer_and_split_status_fields():
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        page = client.get("/").get_data(as_text=True)

    assert 'id="historyDrawer"' in page
    assert 'id="statusTask"' in page
    assert 'id="statusTarget"' in page
    assert "function openHistoryDrawer()" in page


def test_root_homepage_groups_toolbar_actions_for_clearer_hierarchy():
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        page = client.get("/").get_data(as_text=True)

    assert 'class="header-group header-primary"' in page
    assert 'class="header-group header-secondary"' in page
    render_match = re.search(r"function renderTable\(sites\) \{.*?\n\}", page, re.S)

    assert render_match
    assert 'class="actions actions-primary"' in render_match.group(0)
    assert 'class="actions actions-secondary"' in render_match.group(0)


def test_root_homepage_exposes_service_toggle_and_pause_controls():
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        page = client.get("/").get_data(as_text=True)

    assert 'id="btnServiceToggle"' in page
    assert 'function setServiceToggle(enabled)' in page
    assert 'data-action="pause"' in page
    assert "async function toggleSiteCrawl(id, paused)" in page


def test_root_homepage_exposes_rolling_day_week_month_stats_card():
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        page = client.get("/").get_data(as_text=True)

    assert 'id="statsMonthCount"' in page
    assert 'id="statsWeekCount"' in page
    assert 'id="statsDayCount"' in page
    assert "async function loadDashboardStats()" in page
    assert "const res = await fetch('/api/system/stats');" in page
    assert "document.getElementById('statsMonthCount').textContent = String(stats.month_count || 0);" in page
    assert "document.getElementById('statsWeekCount').textContent = String(stats.week_count || 0);" in page
    assert "document.getElementById('statsDayCount').textContent = String(stats.day_count || 0);" in page
    assert "按 JSON 文件名日期计入当月、本周和本日" in page


def test_root_homepage_interval_select_offers_1_to_12_hours():
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        page = client.get("/").get_data(as_text=True)

    for hour in range(1, 13):
        assert f'<option value="{hour}"' in page
    assert '<option value="24"' not in page
    assert "const interval = Number(cfg.crawl_interval_hours || 1);" in page
