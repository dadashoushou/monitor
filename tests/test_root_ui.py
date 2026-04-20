import re

import app as app_module


def test_root_homepage_protects_modal_from_accidental_close_and_submit():
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as client:
        page = client.get("/").get_data(as_text=True)

    assert "function serializeModalForm()" in page
    assert "function hasUnsavedModalChanges()" in page
    assert "function confirmDiscardModalChanges()" in page
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
