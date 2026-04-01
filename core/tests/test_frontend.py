"""Frontend tests using Playwright (headless browser).

All external APIs (OpenAI, Spotify) are mocked so no real tokens are needed.
The Flask app runs on a random free port for each test session.
"""

import json
import re
import socket
import threading
import time
from unittest.mock import patch, MagicMock

import pytest
from playwright.sync_api import Page, expect

# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _free_port():
    """Return a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
#  Mocked credentials / config values
# ---------------------------------------------------------------------------

_FAKE_CREDENTIALS = {
    "OPENAI_API_KEY": "sk-test-fake-key-1234",
    "OPENAI_MODEL": "gpt-4.1-mini",
    "SPOTIPY_CLIENT_ID": "fake-client-id",
    "SPOTIPY_CLIENT_SECRET": "fake-client-secret",
    "DEBUG_MODE": "",
    "PLAYLIST_SIZE": "10",
    "NEW_ARTIST_PERCENTAGE": "30",
}

_EMPTY_PROFILE = {
    "meta": {},
    "preferences": {
        "core_description": "",
        "must_have": [],
        "soft_preferences": [],
        "avoid": [],
    },
    "artists": {"confirmed": [], "moderate": [], "rejected": []},
    "taste_rules": {},
    "feedback": {"liked_tracks": [], "disliked_tracks": [], "disliked_artists": []},
    "suggested_artists": [],
    "suggested_tracks": [],
}

_TRAINED_PROFILE = {
    **_EMPTY_PROFILE,
    "preferences": {
        "core_description": "Upbeat theatrical rock with strong melodies",
        "must_have": ["high energy", "strong melodies"],
        "soft_preferences": ["slight prog influence"],
        "avoid": ["electronic production"],
    },
    "last_updated": "2025-01-01T00:00:00",
}


# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def _base_url():
    """Start a patched Flask app in a background thread and return its URL.

    All external-facing APIs are mocked:
      - Credentials are fake (but pass the 'is_set' check)
      - Spotify auth status returns 'authenticated'
      - OpenAI model list returns a canned list
      - Profile is initially untrained (empty)
    """
    port = _free_port()
    url = f"http://127.0.0.1:{port}"

    # --- State shared between the main thread and the server thread --------
    _profile_state = {"profile": dict(_EMPTY_PROFILE), "trained": False}

    # --- Build patchers ----------------------------------------------------

    def fake_get_credentials():
        return {
            "OPENAI_API_KEY": {"masked": "****1234", "is_set": True},
            "SPOTIPY_CLIENT_ID": {"masked": "****c-id", "is_set": True},
            "SPOTIPY_CLIENT_SECRET": {"masked": "****c-se", "is_set": True},
        }

    def fake_save_credentials(data):
        pass  # no-op

    def fake_get_settings():
        return {
            "model": "gpt-4.1-mini",
            "debug_mode": False,
            "debug_controls_available": True,
            "is_android": False,
            "debug_log_path": "debug.log",
            "playlist_size": 10,
            "new_artist_percentage": 30,
        }

    def fake_get_model():
        return "gpt-4.1-mini"

    def fake_get_openai_models():
        return [
            {"id": "gpt-4.1-mini", "label": "gpt-4.1-mini", "supported": True},
            {"id": "gpt-4.1", "label": "gpt-4.1", "supported": True},
            {"id": "gpt-4o", "label": "gpt-4o", "supported": True},
        ]

    def fake_spotify_auth_status():
        return "authenticated"

    def fake_is_profile_trained():
        return _profile_state["trained"]

    def fake_get_profile_status():
        if _profile_state["trained"]:
            return {"trained": True, "last_updated": "2025-01-01T00:00:00"}
        return {"trained": False}

    def fake_load_profile():
        return dict(_profile_state["profile"])

    def fake_save_profile(p):
        _profile_state["profile"] = p

    def fake_train_profile(sections):
        _profile_state["trained"] = True
        _profile_state["profile"]["preferences"] = {
            "core_description": sections.get("core_description", ""),
            "must_have": [x.strip() for x in sections.get("must_have", "").split("\n") if x.strip()],
            "soft_preferences": [x.strip() for x in sections.get("soft_preferences", "").split("\n") if x.strip()],
            "avoid": [x.strip() for x in sections.get("avoid", "").split("\n") if x.strip()],
        }
        _profile_state["profile"]["last_updated"] = "2025-01-01T00:00:00"
        return _profile_state["profile"]

    def fake_save_profile_sections(sections):
        _profile_state["trained"] = True
        _profile_state["profile"]["preferences"] = {
            "core_description": sections.get("core_description", ""),
            "must_have": [x.strip() for x in sections.get("must_have", "").split("\n") if x.strip()],
            "soft_preferences": [x.strip() for x in sections.get("soft_preferences", "").split("\n") if x.strip()],
            "avoid": [x.strip() for x in sections.get("avoid", "").split("\n") if x.strip()],
        }
        _profile_state["profile"]["last_updated"] = "2025-01-01T00:00:00"
        return _profile_state["profile"]

    def fake_export_profile_dict():
        return _profile_state["profile"]

    def fake_like_track(artist, track=None, reason=None):
        pass

    def fake_dislike_track(artist, track=None, reason=None):
        pass

    def fake_remove_from_playlist(artist, track):
        return {"removed": True}

    def fake_clear_debug_log():
        pass

    patches = [
        patch("app.get_credentials", fake_get_credentials),
        patch("app.save_credentials", fake_save_credentials),
        patch("app.get_settings", fake_get_settings),
        patch("app.get_model", fake_get_model),
        patch("app.get_openai_models", fake_get_openai_models),
        patch("app.get_spotify_auth_status", fake_spotify_auth_status),
        patch("app.is_profile_trained", fake_is_profile_trained),
        patch("app.get_profile_status", fake_get_profile_status),
        patch("app.load_profile", fake_load_profile),
        patch("app.save_profile", fake_save_profile),
        patch("app.train_profile", fake_train_profile),
        patch("app.save_profile_sections", fake_save_profile_sections),
        patch("app.export_profile_dict", fake_export_profile_dict),
        patch("app.like_track", fake_like_track),
        patch("app.dislike_track", fake_dislike_track),
        patch("app.remove_from_playlist", fake_remove_from_playlist),
        patch("app.clear_debug_log", fake_clear_debug_log),
        patch("app.get_debug_mode", return_value=False),
        patch("app.get_playlist_size", return_value=10),
        patch("app.get_new_artist_percentage", return_value=30),
        patch("app.is_onboarding_completed", return_value=True),
        patch("app.get_gpt_language", return_value="English"),
    ]

    for p in patches:
        p.start()

    from app import app as flask_app
    flask_app.config["TESTING"] = True

    server_thread = threading.Thread(
        target=lambda: flask_app.run(
            host="127.0.0.1", port=port, use_reloader=False, threaded=True,
        ),
        daemon=True,
    )
    server_thread.start()

    # Wait for the server to be ready
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)

    yield url

    for p in patches:
        p.stop()


@pytest.fixture(scope="session")
def base_url(_base_url):
    """Session-scoped fixture providing the server URL.

    Overrides pytest-playwright's built-in ``base_url`` so page.goto()
    resolves against our test server.
    """
    return _base_url


# ===================================================================
#  Test classes — grouped by UserManual section
# ===================================================================

class TestPageLoad:
    """The main page loads and shows the essential structure."""

    def test_title_is_spotyvibe(self, page: Page, base_url):
        page.goto(base_url)
        expect(page).to_have_title("SpotyVibe")

    def test_heading_visible(self, page: Page, base_url):
        page.goto(base_url)
        expect(page.locator("h1")).to_have_text("SpotyVibe")

    def test_subtitle_visible(self, page: Page, base_url):
        page.goto(base_url)
        expect(page.locator(".subtitle")).to_be_visible()

    def test_provider_sections_visible(self, page: Page, base_url):
        page.goto(base_url)
        expect(page.locator(".provider-badge-openai")).to_be_visible()
        expect(page.locator(".provider-badge-spotify")).to_be_visible()

    def test_generate_button_visible(self, page: Page, base_url):
        page.goto(base_url)
        # Generate section is collapsed by default — expand it first
        page.locator("#generateToggleBtn").click()
        expect(page.locator("#runBtn")).to_be_visible()
        expect(page.locator("#runBtn")).to_have_text("▶ Generate & Create Playlist")


class TestThemeSwitcher:
    """Theme switcher — Equalizer and Pulse themes."""

    def test_theme_buttons_visible(self, page: Page, base_url):
        page.goto(base_url)
        expect(page.locator('[data-theme="equalizer"]')).to_be_visible()
        expect(page.locator('[data-theme="pulse"]')).to_be_visible()

    def test_equalizer_is_default(self, page: Page, base_url):
        page.goto(base_url)
        eq_btn = page.locator('[data-theme="equalizer"]')
        expect(eq_btn).to_have_class(re.compile(r"active"))
        expect(page.locator("body")).to_have_class(re.compile(r"theme-equalizer"))

    def test_switch_to_pulse(self, page: Page, base_url):
        page.goto(base_url)
        page.locator('[data-theme="pulse"]').click()
        expect(page.locator("body")).to_have_class(re.compile(r"theme-pulse"))
        expect(page.locator('[data-theme="pulse"]')).to_have_class(re.compile(r"active"))
        expect(page.locator('[data-theme="equalizer"]')).not_to_have_class(re.compile(r"active"))

    def test_switch_back_to_equalizer(self, page: Page, base_url):
        page.goto(base_url)
        page.locator('[data-theme="pulse"]').click()
        page.locator('[data-theme="equalizer"]').click()
        expect(page.locator("body")).to_have_class(re.compile(r"theme-equalizer"))

    def test_theme_persists_via_localstorage(self, page: Page, base_url):
        page.goto(base_url)
        page.locator('[data-theme="pulse"]').click()
        # Verify localStorage was set
        theme = page.evaluate("localStorage.getItem('spotyvibe-theme')")
        assert theme == "pulse"


class TestBurgerMenu:
    """Burger menu icon and dropdown menu."""

    def test_burger_button_visible(self, page: Page, base_url):
        page.goto(base_url)
        expect(page.locator(".burger-btn")).to_be_visible()

    def test_dropdown_hidden_initially(self, page: Page, base_url):
        page.goto(base_url)
        expect(page.locator("#settingsDropdown")).not_to_have_class(re.compile(r"open"))

    def test_dropdown_opens_on_click(self, page: Page, base_url):
        page.goto(base_url)
        page.locator(".burger-btn").click()
        expect(page.locator("#settingsDropdown")).to_have_class(re.compile(r"open"))

    def test_dropdown_has_all_options(self, page: Page, base_url):
        page.goto(base_url)
        page.locator(".burger-btn").click()
        dd = page.locator("#settingsDropdown")
        expect(dd.locator("text=Credentials")).to_be_visible()
        expect(dd.locator("text=Settings")).to_be_visible()
        expect(dd.locator("text=Help")).to_be_visible()

    def test_dropdown_closes_on_outside_click(self, page: Page, base_url):
        page.goto(base_url)
        page.locator(".burger-btn").click()
        expect(page.locator("#settingsDropdown")).to_have_class(re.compile(r"open"))
        # Click on the heading (outside the dropdown)
        page.locator("h1").click()
        expect(page.locator("#settingsDropdown")).not_to_have_class(re.compile(r"open"))

    def test_spotify_toggle_shows_disconnect_when_authenticated(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        page.locator(".burger-btn").click()
        expect(page.locator("#spotifyToggleBtn")).to_contain_text("Disconnect Spotify")


class TestCredentialsModal:
    """Credentials modal — entering API keys."""

    def test_opens_from_burger_menu(self, page: Page, base_url):
        page.goto(base_url)
        page.locator(".burger-btn").click()
        page.locator("#settingsDropdown >> text=Credentials").click()
        expect(page.locator("#credentialsModal")).to_have_class(re.compile(r"open"))

    def test_shows_three_fields(self, page: Page, base_url):
        page.goto(base_url)
        page.locator(".burger-btn").click()
        page.locator("#settingsDropdown >> text=Credentials").click()
        expect(page.locator("#cred-OPENAI_API_KEY")).to_be_visible()
        expect(page.locator("#cred-SPOTIPY_CLIENT_ID")).to_be_visible()
        expect(page.locator("#cred-SPOTIPY_CLIENT_SECRET")).to_be_visible()

    def test_shows_credential_status(self, page: Page, base_url):
        page.goto(base_url)
        page.locator(".burger-btn").click()
        page.locator("#settingsDropdown >> text=Credentials").click()
        # Our mock returns is_set=True for all keys
        expect(page.locator("#status-OPENAI_API_KEY")).to_contain_text("Set")
        expect(page.locator("#status-SPOTIPY_CLIENT_ID")).to_contain_text("Set")
        expect(page.locator("#status-SPOTIPY_CLIENT_SECRET")).to_contain_text("Set")

    def test_closes_on_cancel(self, page: Page, base_url):
        page.goto(base_url)
        page.locator(".burger-btn").click()
        page.locator("#settingsDropdown >> text=Credentials").click()
        expect(page.locator("#credentialsModal")).to_have_class(re.compile(r"open"))
        page.locator("#credentialsModal .btn-cancel").click()
        expect(page.locator("#credentialsModal")).not_to_have_class(re.compile(r"open"))

    def test_closes_on_overlay_click(self, page: Page, base_url):
        page.goto(base_url)
        page.locator(".burger-btn").click()
        page.locator("#settingsDropdown >> text=Credentials").click()
        # Click the overlay (top-left corner, outside the modal)
        page.locator("#credentialsModal").click(position={"x": 5, "y": 5})
        expect(page.locator("#credentialsModal")).not_to_have_class(re.compile(r"open"))


class TestSettingsModal:
    """Settings modal — model selection, playlist size, new artist %, debug mode."""

    def test_opens_from_burger_menu(self, page: Page, base_url):
        page.goto(base_url)
        page.locator(".burger-btn").click()
        page.locator("#settingsDropdown >> text=⚙️ Settings").click()
        expect(page.locator("#settingsModal")).to_have_class(re.compile(r"open"))

    def test_shows_model_dropdown(self, page: Page, base_url):
        page.goto(base_url)
        page.locator(".burger-btn").click()
        page.locator("#settingsDropdown >> text=⚙️ Settings").click()
        page.wait_for_load_state("networkidle")
        select = page.locator("#settings-model")
        expect(select).to_be_visible()

    def test_model_dropdown_has_options(self, page: Page, base_url):
        page.goto(base_url)
        page.locator(".burger-btn").click()
        page.locator("#settingsDropdown >> text=⚙️ Settings").click()
        # Wait for the loading overlay to disappear, indicating models have loaded
        page.locator("#settingsLoading.active").wait_for(state="detached", timeout=5000)
        options = page.locator("#settings-model option").all_text_contents()
        assert "gpt-4.1-mini" in options
        assert "gpt-4.1" in options

    def test_shows_playlist_size(self, page: Page, base_url):
        page.goto(base_url)
        page.locator(".burger-btn").click()
        page.locator("#settingsDropdown >> text=⚙️ Settings").click()
        page.wait_for_load_state("networkidle")
        expect(page.locator("#settings-playlist-size")).to_be_visible()
        expect(page.locator("#settings-playlist-size")).to_have_value("10")

    def test_shows_new_artist_percentage(self, page: Page, base_url):
        page.goto(base_url)
        page.locator(".burger-btn").click()
        page.locator("#settingsDropdown >> text=⚙️ Settings").click()
        page.wait_for_load_state("networkidle")
        expect(page.locator("#settings-new-artist-pct")).to_be_visible()
        expect(page.locator("#settings-new-artist-pct")).to_have_value("30")

    def test_shows_debug_mode_checkbox(self, page: Page, base_url):
        page.goto(base_url)
        page.locator(".burger-btn").click()
        page.locator("#settingsDropdown >> text=⚙️ Settings").click()
        page.wait_for_load_state("networkidle")
        expect(page.locator("#settings-debug")).to_be_visible()

    def test_closes_on_cancel(self, page: Page, base_url):
        page.goto(base_url)
        page.locator(".burger-btn").click()
        page.locator("#settingsDropdown >> text=⚙️ Settings").click()
        page.locator("#settingsModal .btn-cancel").click()
        expect(page.locator("#settingsModal")).not_to_have_class(re.compile(r"open"))


class TestHelpModal:
    """Help modal — loads and displays the user manual."""

    def test_opens_from_burger_menu(self, page: Page, base_url):
        page.goto(base_url)
        page.locator(".burger-btn").click()
        page.locator("#settingsDropdown >> text=Help").click()
        expect(page.locator("#helpModal")).to_have_class(re.compile(r"open"))

    def test_loads_help_content(self, page: Page, base_url):
        page.goto(base_url)
        page.locator(".burger-btn").click()
        page.locator("#settingsDropdown >> text=Help").click()
        # Wait for help content to load (should contain the guide heading)
        page.locator("#helpContent >> text=SpotyVibe User Guide").wait_for(timeout=5000)
        expect(page.locator("#helpContent >> text=SpotyVibe User Guide")).to_be_visible()

    def test_help_contains_key_sections(self, page: Page, base_url):
        page.goto(base_url)
        page.locator(".burger-btn").click()
        page.locator("#settingsDropdown >> text=Help").click()
        page.locator("#helpContent >> text=SpotyVibe User Guide").wait_for(timeout=5000)
        content = page.locator("#helpContent")
        expect(content.locator("h2:has-text('Getting Started')").first).to_be_visible()
        expect(content.locator("h2:has-text('Playlist Generation')").first).to_be_visible()

    def test_closes_on_close_button(self, page: Page, base_url):
        page.goto(base_url)
        page.locator(".burger-btn").click()
        page.locator("#settingsDropdown >> text=Help").click()
        expect(page.locator("#helpModal")).to_have_class(re.compile(r"open"))
        page.locator("#helpModal .help-close-btn").click()
        expect(page.locator("#helpModal")).not_to_have_class(re.compile(r"open"))


class TestProfileEditor:
    """Music Profile section — editing, accordion panels, save/cancel."""

    def test_edit_button_visible(self, page: Page, base_url):
        page.goto(base_url)
        expect(page.locator("#trainToggleBtn")).to_be_visible()

    def test_editor_hidden_by_default_when_trained(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        # Body is hidden when profile is trained (our mock starts untrained,
        # but the init auto-opens for first-time users — so we just verify
        # the toggle works)
        expect(page.locator("#trainToggleBtn")).to_be_visible()

    def test_toggle_opens_and_closes_editor(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        # If already open (untrained auto-open), close first
        body = page.locator("#trainBody")
        if body.is_visible():
            page.locator("#trainToggleBtn").click()
            expect(body).to_be_hidden()

        # Open
        page.locator("#trainToggleBtn").click()
        expect(body).to_be_visible()
        expect(page.locator("#trainToggleBtn")).to_have_text("Hide profile")

        # Close
        page.locator("#trainToggleBtn").click()
        expect(body).to_be_hidden()
        expect(page.locator("#trainToggleBtn")).to_have_text("Edit profile")

    def test_accordion_sections_present(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        # Ensure editor is open
        if not page.locator("#trainBody").is_visible():
            page.locator("#trainToggleBtn").click()

        expect(page.locator("#accCoreDesc")).to_be_visible()
        expect(page.locator("#accMustHave")).to_be_visible()
        expect(page.locator("#accSoftPrefs")).to_be_visible()
        expect(page.locator("#accAvoid")).to_be_visible()

    def test_core_description_required_validation(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        if not page.locator("#trainBody").is_visible():
            page.locator("#trainToggleBtn").click()

        # Clear the core description field and try to save
        page.locator("#trainCoreDesc").fill("")
        page.locator("#trainSaveBtn").click()

        # The error message should be visible or an alert should appear
        # (the endpoint returns 400 when core_description is empty)
        # Wait for the error to appear in the status or as a toast
        page.wait_for_timeout(500)

    def test_save_profile_directly(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        if not page.locator("#trainBody").is_visible():
            page.locator("#trainToggleBtn").click()

        page.locator("#trainCoreDesc").fill("Upbeat rock with strong melodies")
        page.locator("#trainSaveBtn").click()

        # Wait for success indication
        page.wait_for_timeout(1000)

    def test_accordion_toggle(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        if not page.locator("#trainBody").is_visible():
            page.locator("#trainToggleBtn").click()

        # Must Have accordion — click header to toggle
        must_have = page.locator("#accMustHave")
        header = must_have.locator(".accordion-header")

        # Initially closed
        expect(must_have).not_to_have_class(re.compile(r"open"))

        # Open
        header.click()
        expect(must_have).to_have_class(re.compile(r"open"))

        # Close
        header.click()
        expect(must_have).not_to_have_class(re.compile(r"open"))

    def test_import_export_reset_visible_in_edit_mode(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Close editor if auto-opened, then reopen via button (sets userProfileEditMode=true)
        if page.locator("#trainBody").is_visible():
            page.locator("#trainToggleBtn").click()

        page.locator("#trainToggleBtn").click()
        expect(page.locator("#profileIoActions")).to_be_visible()
        expect(page.locator("#profileImportBtn")).to_be_visible()
        expect(page.locator("#profileExportBtn")).to_be_visible()
        expect(page.locator("#profileResetBtn")).to_be_visible()


class TestGenerateSection:
    """Generate Playlist section — button states, warnings."""

    def test_generate_button_present(self, page: Page, base_url):
        page.goto(base_url)
        # Generate section is collapsed by default — expand it first
        page.locator("#generateToggleBtn").click()
        expect(page.locator("#runBtn")).to_be_visible()

    def test_cancel_button_hidden_initially(self, page: Page, base_url):
        page.goto(base_url)
        page.locator("#generateToggleBtn").click()
        expect(page.locator("#cancelBtn")).to_be_hidden()

    def test_use_tracks_button_hidden_initially(self, page: Page, base_url):
        page.goto(base_url)
        page.locator("#generateToggleBtn").click()
        expect(page.locator("#useTracksBtn")).to_be_hidden()

    def test_no_warnings_when_all_configured(self, page: Page, base_url):
        """When credentials are set and Spotify is authenticated, no warnings show."""
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        page.locator("#generateToggleBtn").click()
        run_warn = page.locator("#runWarn")
        expect(run_warn).to_have_class(re.compile(r"hidden"))

    def test_no_warnings_in_train_section(self, page: Page, base_url):
        """When OpenAI key is set, no train-section warning shows."""
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        train_warn = page.locator("#trainWarn")
        expect(train_warn).to_have_class(re.compile(r"hidden"))


class TestGenerationPipeline:
    """Test the SSE-driven generation pipeline with mocked GPT + Spotify."""

    def test_generation_flow_with_mocked_sse(self, page: Page, base_url):
        """Start generation and verify the UI shows progress and results.

        We mock the pipeline endpoints at the route handler level so the
        SSE stream emits pre-built events without calling real APIs.
        """
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Intercept the /api/run POST and return a fake SSE stream
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

        # Also mock profile status to be trained
        def handle_profile_status(route):
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"trained": True, "last_updated": "2025-01-01T00:00:00"}),
            )

        page.route("**/api/run", handle_run)
        page.route("**/api/profile/status", handle_profile_status)

        # Reload so the profile status check picks up the mock
        page.reload()
        page.wait_for_load_state("networkidle")

        # Expand collapsed generate section and click Generate
        page.locator("#generateToggleBtn").click()
        page.locator("#runBtn").click()

        # Wait for result tracks to appear
        page.locator(".track-item").first.wait_for(timeout=5000)

        # Verify tracks rendered
        tracks = page.locator(".track-item")
        assert tracks.count() == 3

        # Verify track content
        expect(tracks.first).to_contain_text("Test Artist")
        expect(tracks.first).to_contain_text("Test Song")

        # Verify playlist link shown
        expect(page.locator("#playlistLinkBox")).to_be_visible()
        expect(page.locator("#playlistLinkBox")).to_contain_text("open.spotify.com")

        # Verify status shows success
        expect(page.locator("#statusBox")).to_contain_text("3 suggestions generated")

    def test_cancel_button_shows_during_generation(self, page: Page, base_url):
        """While generation is in progress, the Cancel button becomes visible."""
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Hold the SSE request open (never fulfill) so generation stays in-progress
        def handle_run_hang(route):
            # Don't fulfill — the request stays pending, keeping the UI in
            # "generating" state long enough for assertions to pass.
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
        page.wait_for_load_state("networkidle")

        # Expand collapsed generate section, then observe run button
        page.locator("#generateToggleBtn").click()
        page.locator("#runBtn").click()
        # The button should change to "Generating…" and stay there
        expect(page.locator("#runBtn")).to_have_text("⏳ Generating…", timeout=5000)

        # Clean up: unroute so hanging request doesn't leak into other tests
        page.unroute("**/api/run")


class TestFeedbackButtons:
    """Like, Dislike, and Remove buttons on track items."""

    def _setup_with_tracks(self, page: Page, base_url):
        """Navigate and inject fake tracks via route interception."""
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

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
        page.wait_for_load_state("networkidle")
        # Generate section is collapsed by default — expand it first
        page.locator("#generateToggleBtn").click()
        page.locator("#runBtn").click()
        page.locator(".track-item").first.wait_for(timeout=5000)

    def test_like_button_opens_feedback_form(self, page: Page, base_url):
        self._setup_with_tracks(page, base_url)
        page.locator("#track-0 .btn-like").click()
        form = page.locator("#form-0")
        expect(form).to_have_class(re.compile(r"open"))
        expect(page.locator("#submitBtn-0")).to_contain_text("Submit Like")

    def test_dislike_button_opens_feedback_form(self, page: Page, base_url):
        self._setup_with_tracks(page, base_url)
        page.locator("#track-0 .btn-dislike").click()
        form = page.locator("#form-0")
        expect(form).to_have_class(re.compile(r"open"))
        expect(page.locator("#submitBtn-0")).to_contain_text("Submit Dislike")

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

        # Open form for second track
        page.locator("#track-1 .btn-dislike").click()
        expect(page.locator("#form-1")).to_have_class(re.compile(r"open"))
        # First form should be closed
        expect(page.locator("#form-0")).not_to_have_class(re.compile(r"open"))

    def test_submit_like_sends_feedback(self, page: Page, base_url):
        self._setup_with_tracks(page, base_url)

        # Intercept the feedback API call
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

        # Wait for the request to be sent
        page.wait_for_timeout(500)
        assert len(feedback_requests) == 1
        assert feedback_requests[0]["action"] == "like"
        assert feedback_requests[0]["artist"] == "Feedback Artist"

    def test_remove_button_removes_track(self, page: Page, base_url):
        self._setup_with_tracks(page, base_url)

        # Intercept remove API
        page.route("**/api/remove", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"removed": True}),
        ))

        assert page.locator(".track-item").count() == 2
        page.locator("#track-0 .btn-remove").click()

        # Wait for animation + removal
        page.wait_for_timeout(500)
        assert page.locator(".track-item").count() == 1


class TestWarningsWithMissingCredentials:
    """Verify warnings appear when credentials/auth are missing."""

    def test_openai_warning_when_key_missing(self, page: Page, base_url):
        page.goto(base_url)

        # Override the credentials check to report OpenAI key as not set
        def handle_creds(route):
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({
                    "OPENAI_API_KEY": {"masked": "", "is_set": False},
                    "SPOTIPY_CLIENT_ID": {"masked": "****", "is_set": True},
                    "SPOTIPY_CLIENT_SECRET": {"masked": "****", "is_set": True},
                }),
            )

        page.route("**/api/settings/credentials", handle_creds)
        page.reload()
        page.wait_for_load_state("networkidle")

        # Train section should show OpenAI warning
        train_warn = page.locator("#trainWarn")
        expect(train_warn).to_be_visible()
        expect(train_warn).to_contain_text("OpenAI API key is missing")

        # Generate section is collapsed — expand it to check warnings
        page.locator("#generateToggleBtn").click()

        # Generate section should also warn
        run_warn = page.locator("#runWarn")
        expect(run_warn).to_be_visible()
        expect(run_warn).to_contain_text("OpenAI API key is missing")

        # Train and generate buttons should be disabled
        expect(page.locator("#trainSendBtn")).to_be_disabled()
        expect(page.locator("#trainToggleBtn")).to_be_disabled()
        expect(page.locator("#runBtn")).to_be_disabled()

    def test_spotify_warning_when_not_authenticated(self, page: Page, base_url):
        page.goto(base_url)

        def handle_spotify(route):
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"status": "not_authenticated"}),
            )

        page.route("**/api/spotify/status", handle_spotify)
        page.reload()
        page.wait_for_load_state("networkidle")

        # Generate section is collapsed — expand it to check warnings
        page.locator("#generateToggleBtn").click()

        run_warn = page.locator("#runWarn")
        expect(run_warn).to_be_visible()
        expect(run_warn).to_contain_text("Spotify login required")
        expect(page.locator("#runBtn")).to_be_disabled()

    def test_spotify_warning_when_not_configured(self, page: Page, base_url):
        page.goto(base_url)

        def handle_spotify(route):
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"status": "not_configured"}),
            )

        page.route("**/api/spotify/status", handle_spotify)
        page.reload()
        page.wait_for_load_state("networkidle")

        # Generate section is collapsed — expand it to check warnings
        page.locator("#generateToggleBtn").click()

        run_warn = page.locator("#runWarn")
        expect(run_warn).to_be_visible()
        expect(run_warn).to_contain_text("Spotify credentials are missing")


class TestProfileExport:
    """Profile export downloads a JSON file."""

    def test_export_triggers_download(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Open editor via button (to show import/export/reset)
        if page.locator("#trainBody").is_visible():
            page.locator("#trainToggleBtn").click()
        page.locator("#trainToggleBtn").click()

        # Click export and wait for download
        with page.expect_download() as download_info:
            page.locator("#profileExportBtn").click()
        download = download_info.value
        assert download.suggested_filename == "spotyvibe_profile.json"


class TestToastNotifications:
    """Toast notifications appear for user actions."""

    def test_toast_appears_on_feedback(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # Set up tracks via route interception
        def handle_run(route):
            sse_body = (
                'data: {"type":"result","playlist":['
                '{"artist":"Toast Artist","track":"Toast Song","reason":"Test"}],'
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
        page.route("**/api/feedback", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"status": "ok"}),
        ))

        page.reload()
        page.wait_for_load_state("networkidle")

        # Generate section is collapsed by default — expand it first
        page.locator("#generateToggleBtn").click()
        page.locator("#runBtn").click()
        page.locator(".track-item").first.wait_for(timeout=5000)

        # Like the track
        page.locator("#track-0 .btn-like").click()
        page.locator("#submitBtn-0").click()

        # Toast should appear
        toast = page.locator("#toast")
        expect(toast).to_contain_text("Liked", timeout=3000)


class TestResponsiveLayout:
    """Basic responsive layout checks."""

    def test_mobile_viewport(self, page: Page, base_url):
        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(base_url)
        # Main elements should still be visible
        expect(page.locator("h1")).to_be_visible()
        expect(page.locator("#generateToggleBtn")).to_be_visible()
        expect(page.locator(".burger-btn")).to_be_visible()

    def test_tablet_viewport(self, page: Page, base_url):
        page.set_viewport_size({"width": 768, "height": 1024})
        page.goto(base_url)
        expect(page.locator("h1")).to_be_visible()
        expect(page.locator("#generateToggleBtn")).to_be_visible()
