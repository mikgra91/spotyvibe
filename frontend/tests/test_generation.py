"""Generation pipeline, feedback, playlist modes, refine, audio filters,
run history, and band analysis tests."""

import json
import re

import pytest
from playwright.sync_api import Page, expect

from helpers import (
    switch_to_tab, open_generate_section, open_analysis_section,
    open_review_section, open_audio_filters,
    FAKE_ANALYSIS_RESPONSE, FAKE_PLAYLISTS, FAKE_REVIEW_TRACKS, FAKE_HISTORY,
)


class TestGenerateSection:
    """Generate Playlist section — button states, warnings."""

    def test_generate_button_present(self, page: Page, base_url):
        page.goto(base_url)
        open_generate_section(page)
        expect(page.locator("#runBtn")).to_be_visible()

    def test_cancel_button_hidden_initially(self, page: Page, base_url):
        page.goto(base_url)
        open_generate_section(page)
        expect(page.locator("#cancelBtn")).to_be_hidden()

    def test_use_tracks_button_hidden_initially(self, page: Page, base_url):
        page.goto(base_url)
        open_generate_section(page)
        expect(page.locator("#useTracksBtn")).to_be_hidden()

    def test_no_warnings_when_all_configured(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_generate_section(page)
        run_warn = page.locator("#runWarn")
        expect(run_warn).to_have_class(re.compile(r"hidden"))

    def test_no_warnings_in_train_section(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        train_warn = page.locator("#trainWarn")
        expect(train_warn).to_have_class(re.compile(r"hidden"))


class TestGenerationPipeline:
    """Test the SSE-driven generation pipeline with mocked GPT + Spotify."""

    def test_generation_flow_with_mocked_sse(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")

        def handle_run(route):
            sse_body = (
                'data: {"type":"progress","message":"Batch 1: Asking GPT for 10 suggestions…"}\n\n'
                'data: {"type":"progress","message":"Batch 1: Verifying 3 tracks on Spotify…"}\n\n'
                'data: {"type":"batch_verified","count":3,"total":10}\n\n'
                'data: {"type":"result","playlist":['
                '{"artist":"Test Artist","track":"Test Song","reason":"Great energy"},'
                '{"artist":"Another Band","track":"Cool Track","reason":"Strong melody"},'
                '{"artist":"Third Act","track":"Fire","reason":"Upbeat"}],'
                '"playlist_url":"https://open.spotify.com/playlist/test123",'
                '"added":3,"not_found":[],"was_cancelled":false}\n\n'
            )
            route.fulfill(
                status=200,
                headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
                body=sse_body,
            )

        def handle_profile_status(route):
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"trained": True, "last_updated": "2025-01-01T00:00:00"}),
            )

        page.route("**/api/run", handle_run)
        page.route("**/api/profile/status", handle_profile_status)
        page.reload()
        page.wait_for_load_state("domcontentloaded")

        open_generate_section(page)
        expect(page.locator("#runBtn")).to_be_visible()
        page.locator("#runBtn").click()
        page.locator(".track-item").first.wait_for(timeout=2500)
        tracks = page.locator(".track-item")
        assert tracks.count() == 3
        expect(tracks.first).to_contain_text("Test Artist")
        expect(tracks.first).to_contain_text("Test Song")
        expect(page.locator("#playlistLinkBox")).to_be_visible()
        expect(page.locator("#playlistLinkBox")).to_contain_text("open.spotify.com")
        expect(page.locator("#statusBox")).to_contain_text("3 suggestions generated")

    def test_partial_results_on_cancel(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")

        def handle_run_partial(route):
            sse_body = (
                'data: {"type":"progress","message":"Batch 1: Asking GPT…"}\n\n'
                'data: {"type":"result","playlist":['
                '{"artist":"Partial Artist","track":"Partial Track","reason":"Arrived before cancel"}],'
                '"playlist_url":"https://open.spotify.com/playlist/partial",'
                '"added":1,"not_found":[],"was_cancelled":true}\n\n'
            )
            route.fulfill(
                status=200,
                headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
                body=sse_body,
            )

        def handle_profile_status(route):
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"trained": True, "last_updated": "2025-01-01T00:00:00"}),
            )

        page.route("**/api/run", handle_run_partial)
        page.route("**/api/profile/status", handle_profile_status)
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        open_generate_section(page)
        page.locator("#runBtn").click()
        page.locator(".track-item").first.wait_for(timeout=2500)
        assert page.locator(".track-item").count() >= 1
        expect(page.locator(".track-item").first).to_contain_text("Partial Artist")

    def test_cancel_button_shows_during_generation(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")

        def handle_run_hang(route):
            pass

        def handle_profile_status(route):
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"trained": True, "last_updated": "2025-01-01T00:00:00"}),
            )

        page.route("**/api/run", handle_run_hang)
        page.route("**/api/profile/status", handle_profile_status)
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        open_generate_section(page)
        expect(page.locator("#runBtn")).to_be_visible()
        page.locator("#runBtn").click()
        expect(page.locator("#runBtn")).to_have_text("Generating suggestions…", timeout=2500)
        page.unroute("**/api/run")


class TestFeedbackButtons:
    """Like, Dislike, and Remove buttons on track items."""

    def _setup_with_tracks(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")

        def handle_run(route):
            sse_body = (
                'data: {"type":"result","playlist":['
                '{"artist":"Feedback Artist","track":"Test Track","reason":"Good vibes"},'
                '{"artist":"Second Artist","track":"Another Track","reason":"Nice melody"}],'
                '"playlist_url":"https://open.spotify.com/playlist/test",'
                '"added":2,"not_found":[],"was_cancelled":false}\n\n'
            )
            route.fulfill(
                status=200,
                headers={"Content-Type": "text/event-stream"},
                body=sse_body,
            )

        def handle_profile_status(route):
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"trained": True, "last_updated": "2025-01-01T00:00:00"}),
            )

        page.route("**/api/run", handle_run)
        page.route("**/api/profile/status", handle_profile_status)
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        open_generate_section(page)
        expect(page.locator("#runBtn")).to_be_visible()
        page.locator("#runBtn").click()
        page.locator(".track-item").first.wait_for(timeout=2500)
        assert page.locator(".track-item").count() == 2

    def test_like_button_opens_feedback_form(self, page: Page, base_url):
        self._setup_with_tracks(page, base_url)
        page.locator("#track-0 .btn-like").click()
        form = page.locator("#form-0")
        expect(form).to_have_class(re.compile(r"open"))
        expect(page.locator("#submitBtn-0")).to_contain_text("Submit")

    def test_dislike_button_opens_feedback_form(self, page: Page, base_url):
        self._setup_with_tracks(page, base_url)
        page.locator("#track-0 .btn-dislike").click()
        form = page.locator("#form-0")
        expect(form).to_have_class(re.compile(r"open"))
        expect(page.locator("#submitBtn-0")).to_contain_text("Submit")

    def test_feedback_form_prefills_artist_and_track(self, page: Page, base_url):
        self._setup_with_tracks(page, base_url)
        page.locator("#track-0 .btn-like").click()
        expect(page.locator("#artist-0")).to_have_value("Feedback Artist")
        expect(page.locator("#title-0")).to_have_value("Test Track")

    def test_feedback_form_closes_on_cancel(self, page: Page, base_url):
        self._setup_with_tracks(page, base_url)
        page.locator("#track-0 .btn-like").click()
        expect(page.locator("#form-0")).to_have_class(re.compile(r"open"))
        page.locator("#form-0 .btn-cancel").click()
        expect(page.locator("#form-0")).not_to_have_class(re.compile(r"open"))

    def test_only_one_form_open_at_a_time(self, page: Page, base_url):
        self._setup_with_tracks(page, base_url)
        page.locator("#track-0 .btn-like").click()
        expect(page.locator("#form-0")).to_have_class(re.compile(r"open"))
        page.locator("#track-1 .btn-dislike").click()
        expect(page.locator("#form-1")).to_have_class(re.compile(r"open"))
        expect(page.locator("#form-0")).not_to_have_class(re.compile(r"open"))

    def test_submit_like_sends_feedback(self, page: Page, base_url):
        self._setup_with_tracks(page, base_url)
        feedback_requests = []

        def handle_feedback(route):
            body = route.request.post_data_json
            feedback_requests.append(body)
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"status": "ok"}),
            )

        page.route("**/api/feedback", handle_feedback)
        page.locator("#track-0 .btn-like").click()
        page.locator("#submitBtn-0").click()
        page.wait_for_timeout(250)
        assert len(feedback_requests) == 1
        assert feedback_requests[0]["action"] == "like"
        assert feedback_requests[0]["artist"] == "Feedback Artist"

    def test_submit_dislike_sends_correct_action(self, page: Page, base_url):
        self._setup_with_tracks(page, base_url)
        feedback_requests = []

        def handle_feedback(route):
            body = route.request.post_data_json
            feedback_requests.append(body)
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"status": "ok"}),
            )

        page.route("**/api/feedback", handle_feedback)
        page.locator("#track-0 .btn-dislike").click()
        page.locator("#submitBtn-0").click()
        page.wait_for_timeout(250)
        assert len(feedback_requests) == 1
        assert feedback_requests[0]["action"] == "dislike"
        assert feedback_requests[0]["artist"] == "Feedback Artist"

    def test_remove_button_removes_track(self, page: Page, base_url):
        self._setup_with_tracks(page, base_url)
        page.route("**/api/remove", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"removed": True}),
        ))
        assert page.locator(".track-item").count() == 2
        page.locator("#track-0 .btn-remove").click()
        page.wait_for_timeout(350)
        assert page.locator(".track-item").count() == 1


class TestBandAnalysis:
    """Band/Song Analysis section — toggle, inputs, analyse, results display."""

    def test_analysis_section_toggle(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        switch_to_tab(page, "openai")
        body = page.locator("#analysisBody")
        if body.is_visible():
            page.locator("#analysisToggleBtn").click()
            expect(body).to_be_hidden()
        page.locator("#analysisToggleBtn").click()
        expect(body).to_be_visible()
        expect(page.locator("#analysisToggleBtn")).to_have_text("Hide")

    def test_analysis_inputs_visible(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_analysis_section(page)
        expect(page.locator("#analysisArtist")).to_be_visible()
        expect(page.locator("#analysisTrack")).to_be_visible()
        expect(page.locator("#analysisSendBtn")).to_be_visible()

    def test_analyse_sends_request(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_analysis_section(page)
        analysis_requests = []

        def handle_analyse(route):
            analysis_requests.append(route.request.post_data_json)
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps(FAKE_ANALYSIS_RESPONSE),
            )

        page.route("**/api/analyze", handle_analyse)
        page.locator("#analysisArtist").fill("Muse")
        page.locator("#analysisTrack").fill("Uprising")
        page.locator("#analysisSendBtn").click()
        page.wait_for_timeout(100)
        assert len(analysis_requests) == 1
        assert analysis_requests[0]["artist"] == "Muse"
        assert analysis_requests[0]["track"] == "Uprising"

    def test_analysis_results_display(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_analysis_section(page)
        page.route("**/api/analyze", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps(FAKE_ANALYSIS_RESPONSE),
        ))
        page.locator("#analysisArtist").fill("Muse")
        page.locator("#analysisSendBtn").click()
        result = page.locator("#analysisResult")
        expect(result).to_be_visible(timeout=3000)
        expect(result).not_to_have_class(re.compile(r"hidden"))

    def test_analysis_empty_artist_does_not_submit(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_analysis_section(page)
        api_calls = []
        page.route("**/api/analyze", lambda route: (
            api_calls.append(1), route.continue_()
        ))
        page.locator("#analysisArtist").fill("")
        page.locator("#analysisSendBtn").click()
        page.wait_for_timeout(150)
        assert len(api_calls) == 0
        toast = page.locator("#toast")
        expect(toast).to_be_visible(timeout=1000)

    def test_analysis_toggle_close(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_analysis_section(page)
        page.locator("#analysisToggleBtn").click()
        expect(page.locator("#analysisBody")).to_be_hidden()

    def test_analysis_keyboard_enter_triggers_analyse(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_analysis_section(page)
        analysis_calls = []
        page.route("**/api/analyze", lambda route: (
            analysis_calls.append(1),
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps(FAKE_ANALYSIS_RESPONSE),
            ),
        )[1])
        page.locator("#analysisArtist").fill("Muse")
        page.locator("#analysisArtist").press("Enter")
        page.wait_for_timeout(100)
        assert len(analysis_calls) >= 1


class TestRunHistory:
    """Run History tab — switching, rendering, expand/collapse."""

    def test_history_tab_switch(self, page: Page, base_url):
        page.goto(base_url)
        switch_to_tab(page, "history")
        expect(page.locator("#historyPanel")).to_be_visible()
        expect(page.locator("#providerOpenai")).to_be_hidden()
        expect(page.locator("#providerSpotify")).to_be_hidden()

    def _load_history(self, page: Page, runs_data: list):
        page.route("**/api/runs", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"runs": runs_data}),
        ))
        switch_to_tab(page, "history")
        page.evaluate("loadHistory()")
        page.wait_for_timeout(150)

    def test_history_empty_state(self, page: Page, base_url):
        page.goto(base_url)
        self._load_history(page, [])
        expect(page.locator("#historyPanel")).to_be_visible()
        expect(page.locator("#historyList")).to_contain_text("No runs yet.")

    def test_history_items_render(self, page: Page, base_url):
        page.goto(base_url)
        self._load_history(page, FAKE_HISTORY)
        items = page.locator("#historyList .history-run-item")
        assert items.count() >= 1

    def test_history_item_expand_collapse(self, page: Page, base_url):
        page.goto(base_url)
        self._load_history(page, FAKE_HISTORY)
        item = page.locator("#historyList .history-run-item").first
        expect(item).not_to_have_class(re.compile(r"expanded"))
        item.click()
        expect(item).to_have_class(re.compile(r"expanded"))
        item.click()
        expect(item).not_to_have_class(re.compile(r"expanded"))

    def test_history_item_keyboard_toggle(self, page: Page, base_url):
        page.goto(base_url)
        self._load_history(page, FAKE_HISTORY)
        item = page.locator("#historyList .history-run-item").first
        item.focus()
        page.keyboard.press("Enter")
        expect(item).to_have_class(re.compile(r"expanded"))

    def test_history_playlist_link_present(self, page: Page, base_url):
        page.goto(base_url)
        self._load_history(page, FAKE_HISTORY)
        item = page.locator("#historyList .history-run-item").first
        link = item.locator("a", has_text="Open playlist")
        expect(link).to_have_count(1)


class TestAudioFilters:
    """Audio Filters sub-panel inside the Generate section."""

    def test_audio_filter_toggle(self, page: Page, base_url):
        page.goto(base_url)
        open_generate_section(page)
        page.locator(".gen-mode-btn[data-mode='advanced']").click()
        page.wait_for_timeout(100)
        body = page.locator("#audioFiltersBody")
        expect(body).to_be_hidden()
        page.locator(".audio-filter-toggle").click()
        expect(body).to_be_visible()

    def test_filter_inputs_visible(self, page: Page, base_url):
        page.goto(base_url)
        open_generate_section(page)
        open_audio_filters(page)
        for field_id in ["af-energy-min", "af-energy-max", "af-valence-min",
                          "af-valence-max", "af-tempo-min", "af-tempo-max",
                          "af-danceability-min", "af-danceability-max",
                          "af-acousticness-min", "af-acousticness-max"]:
            expect(page.locator(f"#{field_id}")).to_be_visible()

    def test_filter_input_accepts_values(self, page: Page, base_url):
        page.goto(base_url)
        open_generate_section(page)
        open_audio_filters(page)
        page.locator("#af-energy-min").fill("50")
        page.locator("#af-energy-max").fill("80")
        expect(page.locator("#af-energy-min")).to_have_value("50")
        expect(page.locator("#af-energy-max")).to_have_value("80")

    def test_clear_all_resets_filters(self, page: Page, base_url):
        page.goto(base_url)
        open_generate_section(page)
        open_audio_filters(page)
        page.locator("#af-energy-min").fill("40")
        page.locator("#af-valence-max").fill("70")
        page.locator(".audio-filter-clear-btn").click()
        expect(page.locator("#af-energy-min")).to_have_value("")
        expect(page.locator("#af-valence-max")).to_have_value("")

    def test_filter_panel_closes_again(self, page: Page, base_url):
        page.goto(base_url)
        open_generate_section(page)
        open_audio_filters(page)
        page.locator(".audio-filter-toggle").click()
        expect(page.locator("#audioFiltersBody")).to_be_hidden()


class TestPlaylistMode:
    """Playlist mode radio buttons and conditional UI inside Generate section."""

    def test_create_mode_shows_name_input_by_default(self, page: Page, base_url):
        page.goto(base_url)
        open_generate_section(page)
        expect(page.locator("#playlistNameRow")).to_be_visible()
        expect(page.locator("#playlistNameInput")).to_be_visible()

    def test_picker_row_hidden_in_create_mode(self, page: Page, base_url):
        page.goto(base_url)
        open_generate_section(page)
        expect(page.locator("#playlistPickerRow")).to_be_hidden()

    def test_append_mode_shows_picker(self, page: Page, base_url):
        page.goto(base_url)
        page.route("**/api/playlists", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"playlists": FAKE_PLAYLISTS}),
        ))
        open_generate_section(page)
        page.locator('input[name="playlist_mode"][value="append"]').check()
        expect(page.locator("#playlistPickerRow")).to_be_visible()

    def test_replace_mode_shows_picker(self, page: Page, base_url):
        page.goto(base_url)
        page.route("**/api/playlists", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"playlists": FAKE_PLAYLISTS}),
        ))
        open_generate_section(page)
        page.locator('input[name="playlist_mode"][value="replace"]').check()
        expect(page.locator("#playlistPickerRow")).to_be_visible()

    def test_default_mode_hides_name_and_picker(self, page: Page, base_url):
        page.goto(base_url)
        open_generate_section(page)
        default_radio = page.locator('input[name="playlist_mode"][value="default"]')
        if default_radio.count() == 0:
            return
        default_radio.check()
        expect(page.locator("#playlistNameRow")).to_be_hidden()
        expect(page.locator("#playlistPickerRow")).to_be_hidden()


class TestRefinePlaylist:
    """Refine Playlist section in the Spotify tab."""

    def test_review_section_toggle(self, page: Page, base_url):
        page.goto(base_url)
        switch_to_tab(page, "spotify")
        body = page.locator("#reviewBody")
        if body.is_visible():
            page.locator("#reviewToggleBtn").click()
            expect(body).to_be_hidden()
        page.locator("#reviewToggleBtn").click()
        expect(body).to_be_visible()
        expect(page.locator("#reviewToggleBtn")).to_have_text("Hide")

    def test_review_playlist_picker_visible(self, page: Page, base_url):
        page.goto(base_url)
        page.route("**/api/playlists", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"playlists": FAKE_PLAYLISTS}),
        ))
        open_review_section(page)
        expect(page.locator("#reviewPlaylistPicker")).to_be_visible()
        expect(page.locator("#reviewLoadBtn")).to_be_visible()

    def _setup_review_with_tracks(self, page: Page, base_url: str):
        page.goto(base_url)
        page.route("**/api/playlists", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"playlists": FAKE_PLAYLISTS}),
        ))
        page.route("**/api/playlist/*/tracks", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"tracks": FAKE_REVIEW_TRACKS}),
        ))
        open_review_section(page)
        page.wait_for_timeout(100)
        picker = page.locator("#reviewPlaylistPicker")
        picker.wait_for(state="visible")
        picker.select_option(index=1)
        page.locator("#reviewLoadBtn").click()
        page.locator("#reviewTrackArea").wait_for(state="visible", timeout=5000)

    def test_load_playlist_renders_tracks(self, page: Page, base_url):
        self._setup_review_with_tracks(page, base_url)
        track_items = page.locator("#reviewTrackList .track-item")
        assert track_items.count() >= 1

    def test_review_track_has_feedback_buttons(self, page: Page, base_url):
        self._setup_review_with_tracks(page, base_url)
        first = page.locator("#reviewTrackList .track-item").first
        expect(first.locator(".btn-like")).to_be_visible()
        expect(first.locator(".btn-dislike")).to_be_visible()
        expect(first.locator(".btn-remove")).to_be_visible()


class TestTrackCardAttributes:
    """Verify HTML attributes on generated track cards."""

    def _setup_with_tracks(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")

        def handle_run(route):
            sse_body = (
                'data: {"type":"result","playlist":['
                '{"artist":"Img Artist","track":"Img Song","reason":"Test",'
                '"cover_url":"https://example.com/cover.jpg","track_id":"abc123"}],'
                '"playlist_url":"https://open.spotify.com/playlist/t",'
                '"added":1,"not_found":[],"was_cancelled":false}\n\n'
            )
            route.fulfill(
                status=200,
                headers={"Content-Type": "text/event-stream"},
                body=sse_body,
            )

        def handle_profile_status(route):
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"trained": True, "last_updated": "2025-01-01T00:00:00"}),
            )

        page.route("**/api/run", handle_run)
        page.route("**/api/profile/status", handle_profile_status)
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        open_generate_section(page)
        expect(page.locator("#runBtn")).to_be_visible()
        page.locator("#runBtn").click()
        page.locator(".track-item").first.wait_for(timeout=2500)

    def test_cover_images_have_lazy_loading(self, page: Page, base_url):
        self._setup_with_tracks(page, base_url)
        img = page.locator(".track-cover").first
        expect(img).to_have_attribute("loading", "lazy")

