"""Integration test: Band/Song Analysis + Quick Copy."""
import json
import pytest
from playwright.sync_api import Page, expect
from helpers_integration import (
    create_integration_server, open_analysis_section, ANALYSIS_RESPONSE,
)


@pytest.fixture(scope="session")
def _base_url():
    url, stop = create_integration_server()
    yield url
    stop()

@pytest.fixture(scope="session")
def base_url(_base_url):
    return _base_url


class TestBandSongAnalysisWorkflow:
    """Analyse a song and verify audio features, characteristics, and quick copy."""

    def _run_analysis(self, page: Page, base_url: str):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.route("**/api/analyze", lambda route: route.fulfill(
            status=200, headers={"Content-Type": "application/json"},
            body=json.dumps(ANALYSIS_RESPONSE),
        ))
        open_analysis_section(page)
        page.locator("#analysisArtist").fill("Muse")
        page.locator("#analysisTrack").fill("Uprising")
        page.locator("#analysisSendBtn").click()
        page.locator("#analysisResult .analysis-card").wait_for(state="visible", timeout=5000)
        page.wait_for_timeout(150)

    def test_analysis_result_visible(self, page: Page, base_url):
        self._run_analysis(page, base_url)
        expect(page.locator("#analysisResult")).to_be_visible()

    def test_artist_and_track_in_result(self, page: Page, base_url):
        self._run_analysis(page, base_url)
        result = page.locator("#analysisResult")
        expect(result).to_contain_text("Muse")
        expect(result).to_contain_text("Uprising")

    def test_genre_displayed(self, page: Page, base_url):
        self._run_analysis(page, base_url)
        expect(page.locator("#analysisResult")).to_contain_text("Alternative Rock")

    def test_energy_value_displayed(self, page: Page, base_url):
        self._run_analysis(page, base_url)
        expect(page.locator("#analysisResult")).to_contain_text("85%")

    def test_valence_value_displayed(self, page: Page, base_url):
        self._run_analysis(page, base_url)
        expect(page.locator("#analysisResult")).to_contain_text("65%")

    def test_tempo_value_displayed(self, page: Page, base_url):
        self._run_analysis(page, base_url)
        expect(page.locator("#analysisResult")).to_contain_text("128 BPM")

    def test_danceability_value_displayed(self, page: Page, base_url):
        self._run_analysis(page, base_url)
        expect(page.locator("#analysisResult")).to_contain_text("60%")

    def test_acousticness_value_displayed(self, page: Page, base_url):
        self._run_analysis(page, base_url)
        expect(page.locator("#analysisResult")).to_contain_text("5%")

    def test_profile_suggestions_displayed(self, page: Page, base_url):
        self._run_analysis(page, base_url)
        suggestions = page.locator("#analysisResult .btn-copy-suggestion")
        assert suggestions.count() == 2

    def test_quick_copy_has_correct_value(self, page: Page, base_url):
        self._run_analysis(page, base_url)
        first_btn = page.locator("#analysisResult .btn-copy-suggestion").first
        suggestion_text = first_btn.get_attribute("data-suggestion")
        assert suggestion_text == "High-energy theatrical rock with electronic elements and anthemic choruses"

    def test_filter_buttons_present(self, page: Page, base_url):
        self._run_analysis(page, base_url)
        filter_buttons = page.locator("#analysisResult .af-use-btn")
        assert filter_buttons.count() == 5

    def test_use_all_filters_button_present(self, page: Page, base_url):
        self._run_analysis(page, base_url)
        use_all = page.locator("#analysisResult .af-use-all-btn")
        expect(use_all).to_be_visible()

