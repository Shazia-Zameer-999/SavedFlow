from pathlib import Path

TEMPLATE = Path(__file__).parents[1] / "templates" / "test.html"


def test_library_exposes_real_item_actions_and_safe_external_links():
    page = TEMPLATE.read_text()
    assert "Add to Useful" in page
    assert "Analyze with AI" in page
    assert "Delete Reel" in page
    assert 'target="_blank" rel="noopener noreferrer"' in page


def test_mobile_restore_handlers_preserve_app_state():
    page = TEMPLATE.read_text()
    assert "sessionStorage.setItem(UI_STATE_KEY" in page
    assert 'window.addEventListener("pageshow"' in page
    assert 'window.addEventListener("hashchange"' in page
    assert "restoreUiState();" in page
    assert 'document.visibilityState === "visible"' in page
    assert "refreshActiveView();" in page


def test_frontend_handles_non_json_api_errors():
    page = TEMPLATE.read_text()
    assert 'code: "INVALID_API_RESPONSE"' in page
    assert "SavedFlow server error" in page


def test_frontend_labels_all_analysis_states():
    page = TEMPLATE.read_text()
    assert 'WAITING_FOR_QUOTA: "Waiting for Gemini quota"' in page
    assert "function analysisLabel(status)" in page
    assert "Analysis failed" in page
