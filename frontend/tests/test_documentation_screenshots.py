"""Automated screenshot acquisition for documentation/help.en.md.

Launches the app with mocked APIs, navigates to each section described in
help.en.md, and captures a screenshot into documentation/assets/screenshots/.

These tests are EXCLUDED from routine test runs (``python -m pytest``).
They are meant to be run manually by the developer when documentation
screenshots need to be refreshed:

    python -m pytest frontend/tests/test_documentation_screenshots.py -v

Screenshots are saved relative to the project root:
    documentation/assets/screenshots/<name>.png
"""

import json
import socket
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from playwright.sync_api import Page

# ---------------------------------------------------------------------------
#  Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCREENSHOT_DIR = PROJECT_ROOT / "documentation" / "assets" / "screenshots"

# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _shot(page: Page, name: str):
    """Save a full-page screenshot under SCREENSHOT_DIR."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"{name}.png"
    if path.exists():
        path.unlink()
    page.screenshot(path=str(path), full_page=True)


def _shot_element(page: Page, name: str, selector: str):
    """Save a screenshot of a single element."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"{name}.png"
    if path.exists():
        path.unlink()
    el = page.locator(selector)
    el.screenshot(path=str(path))


_INJECT_TRACKS_JS = """() => {
    const tracks = %s;
    import('/static/js/modules/state.js').then(State => {
        State.setSuggestions(tracks);
        window.renderTracks();
    });
}"""

_INJECT_REVIEW_TRACKS_JS = """() => {
    const tracks = %s;
    import('/static/js/modules/state.js').then(State => {
        State.setReviewTracks(tracks);
        window.renderReviewTracks();
    });
}"""


def _switch_tab(page: Page, tab_name: str):
    """Click a main nav tab (openai, spotify, history) and wait for it to activate."""
    page.locator(f"#tab-{tab_name}").click()
    page.wait_for_timeout(300)


def _inject_discover_tracks(page: Page):
    """Inject mock track data into the discover song list and render."""
    page.evaluate(_INJECT_TRACKS_JS % json.dumps(_FAKE_SONGLIST))


def _inject_review_tracks(page: Page):
    """Inject mock track data into the review track list and render."""
    page.evaluate(_INJECT_REVIEW_TRACKS_JS % json.dumps(_FAKE_SONGLIST))
    page.evaluate("""() => {
        document.getElementById('reviewTrackArea').classList.remove('hidden');
        const counter = document.getElementById('reviewTrackCounter');
        if (counter) counter.textContent = '3 track(s)';
    }""")


# ---------------------------------------------------------------------------
#  Mocked data
# ---------------------------------------------------------------------------

_EMPTY_PROFILE = {
    "name": "",
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
    "name": "Main Profile",
    "preferences": {
        "core_description": "Upbeat, theatrical rock with strong melodic hooks, rich harmonies, and constant momentum. Think Queen meets Bear Ghost.",
        "must_have": ["high energy", "strong memorable melodies", "vocals / singing (no instrumentals)"],
        "soft_preferences": ["slight prog influence", "playful and clever composition"],
        "avoid": ["electronic/synth-heavy production", "slow or mid-tempo songs"],
    },
    "last_updated": "2025-06-15T14:30:00",
    "vibe_description": "",
}

_FAKE_PROFILES = [
    {"id": "profile-1", "name": "Main Profile", "trained": True, "last_updated": "2025-06-15T14:30:00"},
    {"id": "profile-2", "name": "Workout", "trained": True, "last_updated": "2025-06-10T09:00:00"},
    {"id": "profile-3", "name": "Chill", "trained": False, "last_updated": None},
]

_FAKE_SONGLIST = [
    {
        "artist": "Bear Ghost",
        "track": "Necromancin Dancin",
        "title": "Necromancin Dancin",
        "cover_url": "",
        "track_id": "3abc123",
        "spotify_url": "https://open.spotify.com/track/3abc123",
        "artist_url": "https://open.spotify.com/artist/abc",
        "album_url": "https://open.spotify.com/album/abc",
        "reason": "High energy theatrical rock with playful melodies",
    },
    {
        "artist": "Queen",
        "track": "Don't Stop Me Now",
        "title": "Don't Stop Me Now",
        "cover_url": "",
        "track_id": "4def456",
        "spotify_url": "https://open.spotify.com/track/4def456",
        "artist_url": "https://open.spotify.com/artist/def",
        "album_url": "https://open.spotify.com/album/def",
        "reason": "Classic upbeat anthem with theatrical vocals",
    },
    {
        "artist": "Muse",
        "track": "Hysteria",
        "title": "Hysteria",
        "cover_url": "",
        "track_id": "5ghi789",
        "spotify_url": "https://open.spotify.com/track/5ghi789",
        "artist_url": "https://open.spotify.com/artist/ghi",
        "album_url": "https://open.spotify.com/album/ghi",
        "reason": "Intense rock with strong bass line and melodic hooks",
    },
]

_FAKE_HISTORY = [
    {
        "timestamp": "2025-06-15T14:30:00",
        "tracks": [
            {"artist": "Bear Ghost", "track": "Necromancin Dancin"},
            {"artist": "Queen", "track": "Don't Stop Me Now"},
            {"artist": "Muse", "track": "Hysteria"},
        ],
        "playlist_url": "https://open.spotify.com/playlist/abc123",
    },
    {
        "timestamp": "2025-06-14T10:15:00",
        "tracks": [
            {"artist": "Foo Fighters", "track": "Everlong"},
            {"artist": "Arctic Monkeys", "track": "Do I Wanna Know?"},
        ],
        "playlist_url": "https://open.spotify.com/playlist/def456",
    },
]


# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def screenshot_url():
    """Start a patched Flask app with realistic mock data for screenshots."""
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))

    port = _free_port()
    url = f"http://127.0.0.1:{port}"

    _state = {"profile": dict(_TRAINED_PROFILE), "trained": True}

    def fake_get_credentials():
        return {
            "OPENAI_API_KEY": {"masked": "****sk-1234", "is_set": True},
            "SPOTIPY_CLIENT_ID": {"masked": "****c-id", "is_set": True},
            "SPOTIPY_CLIENT_SECRET": {"masked": "****ecret", "is_set": True},
        }

    def fake_get_settings():
        return {
            "model": "gpt-4.1-mini",
            "debug_mode": False,
            "debug_controls_available": True,
            "is_android": False,
            "debug_log_path": "debug.log",
            "prompt_log_path": "prompt.log",
            "playlist_size": 30,
            "new_artist_percentage": 30,
            "gpt_language": "English",
            "ui_language": "en",
            "provider_preset": "openai",
            "llm_base_url": "https://api.openai.com/v1",
            "llm_api_key_required": True,
        }

    def fake_list_profiles():
        return _FAKE_PROFILES

    def fake_get_active_profile_id():
        return "profile-1"

    patches = [
        patch("app.get_credentials", fake_get_credentials),
        patch("app.save_credentials", lambda d: None),
        patch("app.get_settings", fake_get_settings),
        patch("app.get_model", return_value="gpt-4.1-mini"),
        patch("app.get_openai_models", return_value=[
            {"id": "gpt-4.1-mini", "label": "gpt-4.1-mini", "supported": True},
            {"id": "gpt-4.1", "label": "gpt-4.1", "supported": True},
            {"id": "gpt-4o", "label": "gpt-4o", "supported": True},
        ]),
        patch("app.get_spotify_auth_status", return_value="authenticated"),
        patch("app.is_profile_trained", return_value=True),
        patch("app.get_profile_status", return_value={"trained": True, "last_updated": "2025-06-15T14:30:00"}),
        patch("app.load_profile", lambda: dict(_state["profile"])),
        patch("app.save_profile", lambda p: None),
        patch("app.train_profile", lambda s: _state["profile"]),
        patch("app.save_profile_sections", lambda s: _state["profile"]),
        patch("app.export_profile_dict", lambda: _state["profile"]),
        patch("app.like_track", lambda *a, **kw: None),
        patch("app.dislike_track", lambda *a, **kw: None),
        patch("app.remove_from_playlist", lambda *a: {"removed": True}),
        patch("app.clear_debug_log", lambda: None),
        patch("app.get_debug_mode", return_value=False),
        patch("app.get_playlist_size", return_value=30),
        patch("app.get_new_artist_percentage", return_value=30),
        patch("app.is_onboarding_completed", return_value=True),
        patch("app.get_gpt_language", return_value="English"),
        patch("app.list_profiles", fake_list_profiles),
        patch("app.get_active_profile_id", fake_get_active_profile_id),
        patch("app.load_runs", return_value=_FAKE_HISTORY),
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

    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)

    yield url

    for p in patches:
        p.stop()


@pytest.fixture(scope="module")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "locale": "en-US",
        "viewport": {"width": 1280, "height": 900},
    }


# ---------------------------------------------------------------------------
#  Screenshot tests
# ---------------------------------------------------------------------------

@pytest.mark.screenshots
class TestDocumentationScreenshotAcquire:
    """Capture screenshots for every placeholder in documentation/help.en.md.

    Each test method corresponds to one or more > **Screenshot placeholder:**
    entries in help.en.md. Screenshots are saved to:
        documentation/assets/screenshots/<name>.png
    """

    # -- Getting Started ----------------------------------------------------

    def test_01_main_home_screen(self, page: Page, screenshot_url):
        """Screenshot: Main home screen / dashboard"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)
        _shot(page, "01_main_home_screen")

    def test_02_header_controls(self, page: Page, screenshot_url):
        """Screenshot: Header with menu, language, and theme controls"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _shot_element(page, "02_header_controls", "header")

    # -- Account Setup ------------------------------------------------------

    def test_03_burger_menu_open(self, page: Page, screenshot_url):
        """Screenshot: Burger menu open"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
        page.wait_for_timeout(300)
        _shot_element(page, "03_burger_menu_open", ".header-controls")

    def test_04_credentials_modal(self, page: Page, screenshot_url):
        """Screenshot: Credentials form filled in"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
        page.wait_for_timeout(200)
        page.locator("button:has-text('Credentials')").click()
        page.wait_for_timeout(300)
        _shot_element(page, "04_credentials_modal", "#credentialsModal .modal")

    def test_05_settings_modal(self, page: Page, screenshot_url):
        """Screenshot: Settings panel"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
        page.wait_for_timeout(200)
        page.locator("button:has-text('Settings')").click()
        page.wait_for_timeout(300)
        _shot_element(page, "05_settings_modal", "#settingsModal .modal")

    # -- User Preferences ---------------------------------------------------

    def test_06_language_selector(self, page: Page, screenshot_url):
        """Screenshot: Language selector"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _shot_element(page, "06_language_selector", "#langToggle")

    def test_07_theme_switcher(self, page: Page, screenshot_url):
        """Screenshot: Theme switcher"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _shot_element(page, "07_theme_switcher", ".style-switcher")

    # -- Music Profile ------------------------------------------------------

    def test_08_profile_editor_open(self, page: Page, screenshot_url):
        """Screenshot: Music Profile editor open with accordion panels"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        # Expand the profile editor
        page.locator("#trainToggleBtn").click()
        page.wait_for_timeout(400)
        _shot_element(page, "08_profile_editor_open", "#trainSection")

    def test_09_profiles_accordion(self, page: Page, screenshot_url):
        """Screenshot: Profiles card with dropdown and action cards"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator("#trainToggleBtn").click()
        page.wait_for_timeout(600)
        _shot_element(page, "09_profiles_accordion", "#profilesCard")

    def test_10_profile_status(self, page: Page, screenshot_url):
        """Screenshot: Profile status indicators"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator("#trainToggleBtn").click()
        page.wait_for_timeout(400)
        _shot_element(page, "10_profile_status", "#trainSection .train-header-left")

    def test_11_vibe_description(self, page: Page, screenshot_url):
        """Screenshot: Describe Your Vibe field with example text"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator("#trainToggleBtn").click()
        page.wait_for_timeout(400)
        # Type example text into the vibe field
        page.locator("#trainVibeDesc").fill(
            "I love energetic rock with theatrical vocals like Queen. "
            "Surprise me with something new but keep it high-energy and melodic!"
        )
        _shot_element(page, "11_vibe_description", "#accVibeDesc")

    def test_12_core_description(self, page: Page, screenshot_url):
        """Screenshot: Core Description field"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator("#trainToggleBtn").click()
        page.wait_for_timeout(400)
        _shot_element(page, "12_core_description", "#accCoreDesc")

    def test_13_must_have(self, page: Page, screenshot_url):
        """Screenshot: Must Have section"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator("#trainToggleBtn").click()
        page.wait_for_timeout(400)
        # Expand the Must Have accordion
        page.locator("#accMustHave .accordion-header").click()
        page.wait_for_timeout(300)
        _shot_element(page, "13_must_have", "#accMustHave")

    def test_14_soft_preferences(self, page: Page, screenshot_url):
        """Screenshot: Soft Preferences section"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator("#trainToggleBtn").click()
        page.wait_for_timeout(400)
        page.locator("#accSoftPrefs .accordion-header").click()
        page.wait_for_timeout(300)
        _shot_element(page, "14_soft_preferences", "#accSoftPrefs")

    def test_15_avoid(self, page: Page, screenshot_url):
        """Screenshot: Avoid section"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator("#trainToggleBtn").click()
        page.wait_for_timeout(400)
        page.locator("#accAvoid .accordion-header").click()
        page.wait_for_timeout(300)
        _shot_element(page, "15_avoid", "#accAvoid")

    def test_16_save_buttons(self, page: Page, screenshot_url):
        """Screenshot: Save and AI Profile Update buttons"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator("#trainToggleBtn").click()
        page.wait_for_timeout(400)
        _shot_element(page, "16_save_buttons", ".train-actions")

    def test_17_profile_io_controls(self, page: Page, screenshot_url):
        """Screenshot: Profile ⋯ menu dropdown open"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator("#trainToggleBtn").click()
        page.wait_for_timeout(400)
        # Open the profile context menu
        page.locator("#profileMenuTrigger").click()
        page.wait_for_timeout(300)
        _shot_element(page, "17_profile_io_controls", "#profilesCard")

    # -- Band/Song Analysis -------------------------------------------------

    def test_18_analysis_panel(self, page: Page, screenshot_url):
        """Screenshot: Band/Song Analysis panel"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator("#analysisToggleBtn").click()
        page.wait_for_timeout(400)
        _shot_element(page, "18_analysis_panel", "#analysisSection")

    # -- Playlist Generation ------------------------------------------------

    def test_19_discover_section(self, page: Page, screenshot_url):
        """Screenshot: Discover Music section expanded"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(400)
        _shot_element(page, "19_discover_section", "#generateSection")

    def test_20_playlist_mode_selector(self, page: Page, screenshot_url):
        """Screenshot: Playlist mode selector"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(400)
        # Switch to advanced mode where playlist mode row lives
        page.locator(".gen-mode-btn[data-mode='advanced']").click()
        page.wait_for_timeout(300)
        _shot_element(page, "20_playlist_mode_selector", ".playlist-mode-row")

    def test_21_audio_filters(self, page: Page, screenshot_url):
        """Screenshot: Audio Filters sub-panel inside Discover Music"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(300)
        # Switch to advanced mode where audio filters live
        page.locator(".gen-mode-btn[data-mode='advanced']").click()
        page.wait_for_timeout(300)
        # Expand the audio filters sub-panel
        page.locator(".audio-filter-toggle").click()
        page.wait_for_timeout(300)
        # Fill in some example filter values for visual interest
        page.locator("#af-energy-min").fill("60")
        page.locator("#af-energy-max").fill("90")
        page.locator("#af-valence-min").fill("40")
        page.locator("#af-valence-max").fill("80")
        page.locator("#af-tempo-min").fill("120")
        page.locator("#af-tempo-max").fill("160")
        page.wait_for_timeout(200)
        _shot_element(page, "21_audio_filters", "#audioFiltersSection")

    # -- Refine Playlist ----------------------------------------------------

    def test_22_refine_playlist_section(self, page: Page, screenshot_url):
        """Screenshot: Refine Playlist section expanded"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#reviewToggleBtn").click()
        page.wait_for_timeout(400)
        _shot_element(page, "22_refine_playlist_section", "#reviewSection")

    # -- Run History --------------------------------------------------------

    def test_23_run_history(self, page: Page, screenshot_url):
        """Screenshot: Run History section with expanded entry"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "history")
        page.wait_for_timeout(400)
        # Expand the first history entry
        first_entry = page.locator(".history-run-item").first
        if first_entry.is_visible():
            first_entry.click()
            page.wait_for_timeout(300)
        _shot_element(page, "23_run_history", "#historySection")

    # -- Onboarding ---------------------------------------------------------
    #
    # The onboarding flow has 7 steps. `help.en.md` links to
    # `24_onboarding_credentials.png` (step 2 — OpenAI key), so that filename
    # is kept as-is. The other steps are captured below with numbers 45–55.

    def _goto_onboarding_page(self, page: Page, screenshot_url: str, page_index: int):
        """Open /onboarding?replay=1 and advance to the given 0-based step index.

        page_index 0 = Welcome, 1 = OpenAI key, 2 = Spotify cred,
        3 = Connect Spotify, 4 = Seed taste, 5 = Model, 6 = Ready.
        """
        def handle_status(route):
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"completed": False}),
            )
        page.route("**/api/onboarding/status", handle_status)
        page.goto(screenshot_url + "/onboarding?replay=1")
        page.wait_for_load_state("networkidle")
        for i in range(page_index):
            # Click the visible CTA inside the currently-active page.
            cta = page.locator(".ob-page.active .ob-cta-next, .ob-page.active .ob-cta-start, .ob-page.active .ob-cta-skip-inline").first
            cta.click()
            page.wait_for_timeout(500)
        page.wait_for_timeout(200)

    def test_24_onboarding_credentials(self, page: Page, screenshot_url):
        """Screenshot: Onboarding step 2 — OpenAI API key (kept at this filename
        because documentation/help.en.md links to it)."""
        self._goto_onboarding_page(page, screenshot_url, page_index=1)
        _shot(page, "24_onboarding_credentials")

    # -- Full-page composite screenshots ------------------------------------

    def test_25_full_page_all_expanded(self, page: Page, screenshot_url):
        """Screenshot: Full page with profile editor and analysis sections open"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        # Expand profile editor
        page.locator("#trainToggleBtn").click()
        page.wait_for_timeout(300)
        # Expand analysis section (same tab)
        page.locator("#analysisToggleBtn").click()
        page.wait_for_timeout(300)
        _shot(page, "25_full_page_all_expanded")

    # -- Quick Start --------------------------------------------------------

    def test_26_quickstart_toc(self, page: Page, screenshot_url):
        """Screenshot placeholder: Quick Start guide contents page with workflow map and TOC entries."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        # Remove the quickstart-dismissed flag so the modal can open
        page.evaluate("localStorage.removeItem('spotyvibe-quickstart-dismissed')")
        page.evaluate("openQuickstart(true)")
        page.wait_for_timeout(500)
        _shot_element(page, "26_quickstart_toc", "#quickstartModal .quickstart-modal")

    # -- Connect to Spotify banner ------------------------------------------

    def test_27_connect_spotify_banner(self, page: Page, screenshot_url):
        """Screenshot placeholder: Connect to Spotify banner"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        # Expand the Discover section
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(300)
        # Simulate Spotify not authenticated state
        page.evaluate("""() => {
            const warn = document.getElementById('runWarn');
            warn.className = '';
            warn.innerHTML = '<span class=\"component-warn\">⚠️ Spotify login required — <a style=\"cursor:pointer;color:var(--primary)\">Connect to Spotify</a>.</span>';
            document.getElementById('runBtn').disabled = true;
            // Update dep chip
            const chip = document.querySelector('#depSpotify .dep-dot');
            if (chip) { chip.className = 'dep-dot dep-dot--error'; }
        }""")
        page.wait_for_timeout(200)
        _shot_element(page, "27_connect_spotify_banner", "#generateSection")

    # -- Profile editing ----------------------------------------------------

    def test_28_editing_existing_profile(self, page: Page, screenshot_url):
        """Screenshot placeholder: Editing an existing profile"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator("#trainToggleBtn").click()
        page.wait_for_timeout(400)
        # Fill in vibe description to show an "editing" state
        page.locator("#trainVibeDesc").fill(
            "I love energetic rock with theatrical vocals like Queen. "
            "Surprise me with something new but keep it high-energy and melodic!"
        )
        # Open the Core Description accordion and fill it
        page.locator("#accCoreDesc .accordion-header").click()
        page.wait_for_timeout(200)
        page.locator("#trainCoreDesc").fill(
            "Upbeat, theatrical rock with strong melodic hooks, rich harmonies, "
            "and constant momentum. Think Queen meets Bear Ghost."
        )
        page.wait_for_timeout(200)
        _shot_element(page, "28_editing_existing_profile", "#trainSection")

    # -- Generation in progress ---------------------------------------------

    def test_29_generation_spinner(self, page: Page, screenshot_url):
        """Screenshot placeholder: Generation in progress with inline spinner"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(300)
        page.evaluate("""() => {
            document.getElementById('generateLoadingArea').classList.remove('hidden');
            document.getElementById('generateLoadingMsg').textContent = 'Getting suggestions from GPT… (12 / 30)';
            const btn = document.getElementById('runBtn');
            btn.disabled = true;
            btn.textContent = '⏳ Generating…';
            document.getElementById('cancelBtn').classList.remove('hidden');
        }""")
        page.wait_for_timeout(300)
        _shot_element(page, "29_generation_spinner", "#generateSection")

    def test_30_cancel_use_tracks_buttons(self, page: Page, screenshot_url):
        """Screenshot placeholder: Cancel and Use X Tracks Now buttons"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(300)
        page.evaluate("""() => {
            document.getElementById('generateLoadingArea').classList.remove('hidden');
            document.getElementById('generateLoadingMsg').textContent = 'Getting suggestions from GPT… (18 / 30)';
            const btn = document.getElementById('runBtn');
            btn.disabled = true;
            btn.textContent = '⏳ Generating…';
            document.getElementById('cancelBtn').classList.remove('hidden');
            const useBtn = document.getElementById('useTracksBtn');
            useBtn.classList.remove('hidden');
            useBtn.textContent = '▶ Use 18 tracks now';
        }""")
        page.wait_for_timeout(200)
        _shot_element(page, "30_cancel_use_tracks", "#generateSection .run-section")

    # -- Track cards --------------------------------------------------------

    def test_31_track_cards(self, page: Page, screenshot_url):
        """Screenshot placeholder: Track cards after generation"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(300)
        _inject_discover_tracks(page)
        page.wait_for_timeout(300)
        _shot_element(page, "31_track_cards", "#discoverTrackArea")

    def test_32_preview_player(self, page: Page, screenshot_url):
        """Screenshot placeholder: Preview player open"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(300)
        _inject_discover_tracks(page)
        page.wait_for_timeout(300)
        # Open preview overlay manually (skip iframe load)
        page.evaluate("""() => {
            const overlay = document.getElementById('spotifyPreviewOverlay');
            overlay.classList.add('visible');
            document.getElementById('spotifyPreviewTitle').textContent = 'Bear Ghost — Necromancin Dancin';
            document.getElementById('previewCounter').textContent = '1 / 3';
        }""")
        page.wait_for_timeout(300)
        _shot_element(page, "32_preview_player", "#spotifyPreviewOverlay")

    def test_33_spotify_quick_links(self, page: Page, screenshot_url):
        """Screenshot placeholder: Spotify quick links on a song card"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(300)
        _inject_discover_tracks(page)
        page.wait_for_timeout(300)
        _shot_element(page, "33_spotify_quick_links", "#track-0 .track-header")

    def test_34_like_feedback_form(self, page: Page, screenshot_url):
        """Screenshot placeholder: Like feedback form"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(300)
        _inject_discover_tracks(page)
        page.wait_for_timeout(300)
        page.evaluate("toggleFeedback(0, 'like')")
        page.wait_for_timeout(200)
        _shot_element(page, "34_like_feedback_form", "#track-0")

    def test_35_dislike_feedback_form(self, page: Page, screenshot_url):
        """Screenshot placeholder: Dislike feedback form"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(300)
        _inject_discover_tracks(page)
        page.wait_for_timeout(300)
        page.evaluate("toggleFeedback(1, 'dislike')")
        page.wait_for_timeout(200)
        _shot_element(page, "35_dislike_feedback_form", "#track-1")

    def test_36_remove_button(self, page: Page, screenshot_url):
        """Screenshot placeholder: Remove button on song card"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(300)
        _inject_discover_tracks(page)
        page.wait_for_timeout(300)
        _shot_element(page, "36_remove_button", "#track-0 .track-actions")

    # -- Refine Playlist tracks ---------------------------------------------

    def test_37_playlist_dropdown(self, page: Page, screenshot_url):
        """Screenshot placeholder: Playlist dropdown with playlists loaded"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#reviewToggleBtn").click()
        page.wait_for_timeout(300)
        # Inject mock playlist options
        page.evaluate("""() => {
            const picker = document.getElementById('reviewPlaylistPicker');
            picker.innerHTML = '<option value="">Select a playlist…</option>'
                + '<option value="pl1">🎵 My Weekend Vibes (25 tracks)</option>'
                + '<option value="pl2">🎵 Road Trip Mix (18 tracks)</option>'
                + '<option value="pl3">🎵 Focus Flow (30 tracks)</option>';
        }""")
        page.wait_for_timeout(200)
        _shot_element(page, "37_playlist_dropdown", "#reviewSection")

    def test_38_review_track_cards(self, page: Page, screenshot_url):
        """Screenshot placeholder: Review track cards"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#reviewToggleBtn").click()
        page.wait_for_timeout(300)
        _inject_review_tracks(page)
        page.wait_for_timeout(300)
        _shot_element(page, "38_review_track_cards", "#reviewTrackArea")

    def test_39_review_like_form(self, page: Page, screenshot_url):
        """Screenshot placeholder: Like feedback form in Refine section"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#reviewToggleBtn").click()
        page.wait_for_timeout(300)
        _inject_review_tracks(page)
        page.wait_for_timeout(300)
        page.evaluate("toggleReviewFeedback(0, 'like')")
        page.wait_for_timeout(200)
        _shot_element(page, "39_review_like_form", "#review-track-0")

    def test_40_review_dislike_form(self, page: Page, screenshot_url):
        """Screenshot placeholder: Dislike feedback form in Refine section"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#reviewToggleBtn").click()
        page.wait_for_timeout(300)
        _inject_review_tracks(page)
        page.wait_for_timeout(300)
        page.evaluate("toggleReviewFeedback(1, 'dislike')")
        page.wait_for_timeout(200)
        _shot_element(page, "40_review_dislike_form", "#review-track-1")

    def test_41_review_dismiss_button(self, page: Page, screenshot_url):
        """Screenshot placeholder: Dismiss button on review track card"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#reviewToggleBtn").click()
        page.wait_for_timeout(300)
        _inject_review_tracks(page)
        page.wait_for_timeout(300)
        _shot_element(page, "41_review_dismiss_button", "#review-track-0 .track-actions")

    # -- Run History song list ----------------------------------------------

    def test_42_history_song_list(self, page: Page, screenshot_url):
        """Screenshot placeholder: Song list with saved tracks"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "history")
        page.wait_for_timeout(400)
        # Expand the first history entry to show its track list
        first_entry = page.locator(".history-run-item").first
        if first_entry.is_visible():
            first_entry.click()
            page.wait_for_timeout(300)
        _shot_element(page, "42_history_song_list", "#historySection")

    # -- Mobile view --------------------------------------------------------

    def test_43_mobile_view(self, page: Page, screenshot_url):
        """Screenshot placeholder: Mobile view of the home screen"""
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)
        _shot(page, "43_mobile_view")
        # Reset viewport for subsequent tests
        page.set_viewport_size({"width": 1280, "height": 900})

    # -- Warning / error message --------------------------------------------

    def test_44_warning_message(self, page: Page, screenshot_url):
        """Screenshot placeholder: Example warning or error message"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(300)
        # Simulate missing OpenAI key warning
        page.evaluate("""() => {
            const warn = document.getElementById('runWarn');
            warn.className = '';
            warn.innerHTML = '<span class=\"component-warn\">⚠️ OpenAI API key is missing — open <a style=\"cursor:pointer;color:var(--primary)\">⚙️ Settings</a> to enter it.</span>';
            document.getElementById('runBtn').disabled = true;
        }""")
        page.wait_for_timeout(200)
        _shot_element(page, "44_warning_message", "#runWarn")

    # -- Onboarding (all 7 steps + overlays) ----------------------------------
    #
    # Step 2 (OpenAI key) is captured above as `24_onboarding_credentials.png`
    # (kept at that number because `documentation/help.en.md` links to it).

    def test_45_onboarding_step1_welcome(self, page: Page, screenshot_url):
        """Screenshot: Onboarding step 1 — welcome / intro with feature bullets."""
        self._goto_onboarding_page(page, screenshot_url, page_index=0)
        _shot(page, "45_onboarding_step1_welcome")

    def test_46_onboarding_step3_spotify_cred(self, page: Page, screenshot_url):
        """Screenshot: Onboarding step 3 — Spotify developer app credentials."""
        self._goto_onboarding_page(page, screenshot_url, page_index=2)
        _shot(page, "46_onboarding_step3_spotify_cred")

    def test_47_onboarding_step4_connect(self, page: Page, screenshot_url):
        """Screenshot: Onboarding step 4 — Connect Spotify account."""
        self._goto_onboarding_page(page, screenshot_url, page_index=3)
        _shot(page, "47_onboarding_step4_connect")

    def test_48_onboarding_step5_seed(self, page: Page, screenshot_url):
        """Screenshot: Onboarding step 5 — Seed your taste (3 cards)."""
        self._goto_onboarding_page(page, screenshot_url, page_index=4)
        _shot(page, "48_onboarding_step5_seed")

    def test_49_onboarding_step6_model(self, page: Page, screenshot_url):
        """Screenshot: Onboarding step 6 — Pick a model."""
        self._goto_onboarding_page(page, screenshot_url, page_index=5)
        _shot(page, "49_onboarding_step6_model")

    def test_50_onboarding_step7_ready(self, page: Page, screenshot_url):
        """Screenshot: Onboarding step 7 — Ready summary."""
        self._goto_onboarding_page(page, screenshot_url, page_index=6)
        _shot(page, "50_onboarding_step7_ready")

    def test_51_onboarding_howto_openai_expanded(self, page: Page, screenshot_url):
        """Screenshot: Step 2 with the 'How do I get this?' accordion expanded."""
        self._goto_onboarding_page(page, screenshot_url, page_index=1)
        page.locator(".ob-cred-guide-toggle").first.click()
        page.wait_for_timeout(250)
        _shot(page, "51_onboarding_howto_openai_expanded")

    def test_52_setup_guide_openai_overlay(self, page: Page, screenshot_url):
        """Screenshot: The full-screen OpenAI setup guide overlay."""
        self._goto_onboarding_page(page, screenshot_url, page_index=1)
        page.locator(".ob-cred-guide-toggle").first.click()
        page.wait_for_timeout(250)
        page.locator(".ob-cred-guide-readmore").first.click()
        page.wait_for_timeout(400)
        _shot(page, "52_setup_guide_openai")

    def test_53_setup_guide_spotify_overlay(self, page: Page, screenshot_url):
        """Screenshot: The full-screen Spotify setup guide overlay."""
        self._goto_onboarding_page(page, screenshot_url, page_index=2)
        page.locator(".ob-page.active .ob-cred-guide-toggle").click()
        page.wait_for_timeout(250)
        page.locator(".ob-page.active .ob-cred-guide-readmore").click()
        page.wait_for_timeout(400)
        _shot(page, "53_setup_guide_spotify")

    def test_54_privacy_modal(self, page: Page, screenshot_url):
        """Screenshot: Privacy 'What gets sent where?' modal, opened from step 1."""
        self._goto_onboarding_page(page, screenshot_url, page_index=0)
        page.locator(".ob-privacy-link").click()
        page.wait_for_timeout(300)
        _shot_element(page, "54_privacy_modal", "#privacyModal .modal")

    def test_55_rerun_setup_menu_item(self, page: Page, screenshot_url):
        """Screenshot: The gear-menu burger with 'Re-run setup' visible."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator("button[aria-label='Menu']").click()
        page.wait_for_timeout(300)
        _shot_element(page, "55_rerun_setup_menu_item", ".header-controls")

    # -- Wave 2: Quick wins ------------------------------------------------

    def test_56_generate_quick_mode(self, page: Page, screenshot_url):
        """Screenshot: Generate panel in Quick mode with exploration slider."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.evaluate("localStorage.setItem('sv.gen_mode', 'quick')")
        page.reload()
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(400)
        _shot_element(page, "56_generate_quick_mode", "#generateSection")

    def test_57_generate_advanced_mode(self, page: Page, screenshot_url):
        """Screenshot: Generate panel in Advanced mode with all controls visible."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(300)
        page.locator(".gen-mode-btn[data-mode='advanced']").click()
        page.wait_for_timeout(300)
        _shot_element(page, "57_generate_advanced_mode", "#generateSection")

    def test_58_exploration_slider_adventurous(self, page: Page, screenshot_url):
        """Screenshot: Exploration slider at notch 5 (Adventurous)."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(300)
        page.evaluate("document.getElementById('explorationSliderQuick').value = 5; document.getElementById('explorationSliderQuick').dispatchEvent(new Event('input'));")
        page.wait_for_timeout(200)
        _shot_element(page, "58_exploration_slider_adventurous", ".gen-mode-body--quick .exploration-row")

    def test_59_exploration_slider_custom(self, page: Page, screenshot_url):
        """Screenshot: Slider in 'Custom' state after Advanced-mode override."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(300)
        page.locator(".gen-mode-btn[data-mode='advanced']").click()
        page.wait_for_timeout(200)
        page.locator("#genNewArtistPct").fill("33")
        page.locator("body").click()
        page.wait_for_timeout(300)
        _shot_element(page, "59_exploration_slider_custom", ".gen-mode-body--advanced .exploration-row")

    def test_60_preset_dropdown_open(self, page: Page, screenshot_url):
        """Screenshot: Preset dropdown expanded in Advanced mode."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.evaluate("""() => {
            const userPresets = [
                { id: 'user_1', name: 'Morning coffee', builtin: false, version: 1, settings: {} },
                { id: 'user_2', name: 'Workout mix',    builtin: false, version: 1, settings: {} },
            ];
            localStorage.setItem('sv.presets.user', JSON.stringify(userPresets));
        }""")
        page.reload()
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(300)
        page.locator(".gen-mode-btn[data-mode='advanced']").click()
        page.wait_for_timeout(200)
        page.locator("#presetDropdownTrigger").click()
        page.wait_for_timeout(200)
        _shot_element(page, "60_preset_dropdown_open", ".preset-row")

    def test_61_preset_dropdown_empty_user(self, page: Page, screenshot_url):
        """Screenshot: Preset dropdown when user has zero custom presets."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.evaluate("localStorage.removeItem('sv.presets.user')")
        page.reload()
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(300)
        page.locator(".gen-mode-btn[data-mode='advanced']").click()
        page.wait_for_timeout(200)
        page.locator("#presetDropdownTrigger").click()
        page.wait_for_timeout(200)
        _shot_element(page, "61_preset_dropdown_empty_user", ".preset-row")

    def test_62_save_preset_dialog(self, page: Page, screenshot_url):
        """Screenshot: 'Save current as preset' dialog."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(300)
        page.locator(".gen-mode-btn[data-mode='advanced']").click()
        page.wait_for_timeout(200)
        page.locator(".preset-save-btn").click()
        page.wait_for_timeout(300)
        _shot_element(page, "62_save_preset_dialog", "#savePresetModal .modal")

    def test_63_preset_manager(self, page: Page, screenshot_url):
        """Screenshot: Manage presets modal with user + built-in rows."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.evaluate("""() => {
            const userPresets = [
                { id: 'user_1', name: 'Morning coffee', builtin: false, version: 1, settings: {} },
                { id: 'user_2', name: 'Workout mix',    builtin: false, version: 1, settings: {} },
            ];
            localStorage.setItem('sv.presets.user', JSON.stringify(userPresets));
        }""")
        page.reload()
        page.wait_for_load_state("networkidle")
        page.locator("button[aria-label='Menu']").click()
        page.wait_for_timeout(200)
        page.locator("button:has-text('Manage presets')").click()
        page.wait_for_timeout(300)
        _shot_element(page, "63_preset_manager", "#presetManagerModal .modal")

    def test_64_completeness_meter_weak(self, page: Page, screenshot_url):
        """Screenshot: Completeness meter at low score (red) on an empty profile."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator("#trainToggleBtn").click()
        page.wait_for_timeout(400)
        page.evaluate("""() => {
            document.getElementById('trainCoreDesc').value = '';
            document.getElementById('trainMustHave').value = '';
            document.getElementById('trainSoftPrefs').value = '';
            document.getElementById('trainAvoid').value = '';
            ['trainCoreDesc','trainMustHave','trainSoftPrefs','trainAvoid'].forEach(id => {
                document.getElementById(id).dispatchEvent(new Event('input'));
            });
        }""")
        page.wait_for_timeout(400)
        _shot_element(page, "64_completeness_meter_weak", "#profileCompletenessCard")

    def test_65_completeness_meter_medium(self, page: Page, screenshot_url):
        """Screenshot: Completeness meter at ~45% (yellow)."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator("#trainToggleBtn").click()
        page.wait_for_timeout(400)
        page.evaluate("""() => {
            document.getElementById('trainCoreDesc').value = 'Upbeat melodic rock.';
            document.getElementById('trainMustHave').value = 'high energy';
            document.getElementById('trainSoftPrefs').value = '';
            document.getElementById('trainAvoid').value = '';
            ['trainCoreDesc','trainMustHave','trainSoftPrefs','trainAvoid'].forEach(id => {
                document.getElementById(id).dispatchEvent(new Event('input'));
            });
        }""")
        page.wait_for_timeout(400)
        _shot_element(page, "65_completeness_meter_medium", "#profileCompletenessCard")

    def test_66_audio_filter_inline_hints(self, page: Page, screenshot_url):
        """Screenshot: Audio filter panel showing inline hints."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(300)
        page.locator(".gen-mode-btn[data-mode='advanced']").click()
        page.wait_for_timeout(200)
        page.locator(".audio-filter-toggle").click()
        page.wait_for_timeout(200)
        page.locator(".audio-filter-row:has-text('Energy') .learn-more > summary").click()
        page.wait_for_timeout(200)
        _shot_element(page, "66_audio_filter_inline_hints", "#audioFiltersSection")

    def test_67_settings_modal_inline_hints(self, page: Page, screenshot_url):
        """Screenshot: Settings modal with new inline hints."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator("button[aria-label='Menu']").click()
        page.wait_for_timeout(200)
        page.locator("button:has-text('Settings')").click()
        page.wait_for_timeout(300)
        _shot_element(page, "67_settings_modal_inline_hints", "#settingsModal .modal")

    def test_68_gen_mode_tabs_isolated(self, page: Page, screenshot_url):
        """Screenshot: The Quick / Advanced tab row."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(300)
        _shot_element(page, "68_gen_mode_tabs", ".gen-mode-tabs")

    # -- Wave 3: New features ---------------------------------------------

    def test_69_playlist_seed_modal(self, page: Page, screenshot_url):
        """Screenshot: playlist-seed picker modal (from action card)."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator("#trainToggleBtn").click()
        page.wait_for_timeout(300)
        # Enable the seed card (requires Spotify auth state)
        page.evaluate("""() => {
            const card = document.getElementById('profileSeedCard');
            if (card) card.classList.remove('disabled');
            const btn = document.getElementById('profileSeedBtn');
            if (btn) btn.disabled = false;
        }""")
        page.locator("#profileSeedBtn").click()
        page.wait_for_timeout(400)
        page.evaluate("""() => {
            const list = document.getElementById('playlistSeedList');
            list.innerHTML = '';
            const samples = [
                { id: 'a', name: 'Road Trip Mix', owner: 'Jane', track_count: 25, cover_url: '' },
                { id: 'b', name: 'Weekend Vibes', owner: 'Jane', track_count: 40, cover_url: '' },
                { id: 'c', name: 'Focus Flow',    owner: 'Jane', track_count: 30, cover_url: '' },
            ];
            samples.forEach(p => {
                const li = document.createElement('li');
                li.className = 'playlist-seed-item';
                li.innerHTML = `<div class="playlist-seed-cover"></div><div class="playlist-seed-text"><div class="playlist-seed-name">${p.name}</div><div class="playlist-seed-meta">${p.track_count} tracks · by ${p.owner}</div></div><div class="playlist-seed-check"></div>`;
                list.appendChild(li);
            });
        }""")
        page.wait_for_timeout(200)
        _shot_element(page, "69_playlist_seed_modal", "#playlistSeedModal .modal")

    def test_70_playlist_seed_drafting(self, page: Page, screenshot_url):
        """Screenshot: picker modal in drafting state with spinner."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator("#trainToggleBtn").click()
        page.wait_for_timeout(300)
        # Enable seed card and open picker
        page.evaluate("""() => {
            const card = document.getElementById('profileSeedCard');
            if (card) card.classList.remove('disabled');
            const btn = document.getElementById('profileSeedBtn');
            if (btn) btn.disabled = false;
        }""")
        page.locator("#profileSeedBtn").click()
        page.wait_for_timeout(300)
        page.evaluate("document.querySelector('.playlist-seed-loader').classList.remove('hidden')")
        page.evaluate("document.getElementById('playlistSeedList').classList.add('hidden')")
        _shot_element(page, "70_playlist_seed_drafting", "#playlistSeedModal .modal")

    def test_71_profile_draft_banner(self, page: Page, screenshot_url):
        """Screenshot: draft banner on the profile editor after a seed."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator("#trainToggleBtn").click()
        page.wait_for_timeout(300)
        page.evaluate("""() => {
            const b = document.getElementById('profileDraftBanner');
            b.classList.remove('hidden');
            document.getElementById('profileDraftSub').textContent = 'Generated from "Road Trip Mix" — review and save below.';
        }""")
        page.wait_for_timeout(200)
        _shot_element(page, "71_profile_draft_banner", "#trainSection")

    def test_72_rationale_chips_default(self, page: Page, screenshot_url):
        """Screenshot: track card with default chip pair (profile_match + artist_match)."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(300)
        page.evaluate(_INJECT_TRACKS_JS % json.dumps([{
            **_FAKE_SONGLIST[0],
            "rationale": [
                {"type": "profile_match", "arg": "theatrical rock"},
                {"type": "artist_match",  "arg": "Queen"},
            ],
        }]))
        page.wait_for_timeout(400)
        _shot_element(page, "72_rationale_chips_default", "#track-0")

    def test_73_rationale_chips_fallback(self, page: Page, screenshot_url):
        """Screenshot: track card with fallback chip (no rationale returned)."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(300)
        page.evaluate(_INJECT_TRACKS_JS % json.dumps([{
            **_FAKE_SONGLIST[0],
            "rationale": [{"type": "fallback"}],
        }]))
        page.wait_for_timeout(400)
        _shot_element(page, "73_rationale_chips_fallback", "#track-0")

    def test_74_rationale_chips_all_types(self, page: Page, screenshot_url):
        """Screenshot: multiple rows showcasing each chip type."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(300)
        tracks = [
            {**_FAKE_SONGLIST[0], "rationale": [{"type": "profile_match", "arg": "indie rock"}]},
            {**_FAKE_SONGLIST[1], "rationale": [{"type": "artist_match", "arg": "Foo Fighters"}]},
            {**_FAKE_SONGLIST[2], "rationale": [{"type": "recency", "arg": "released 2025"}]},
        ]
        page.evaluate(_INJECT_TRACKS_JS % json.dumps(tracks))
        page.wait_for_timeout(400)
        _shot_element(page, "74_rationale_chips_all_types", "#discoverTrackArea")

    def test_75_taste_dashboard(self, page: Page, screenshot_url):
        """Screenshot: taste dashboard with all three charts populated."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.route("**/api/taste/aggregate", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "tracks_considered": 87,
                "runs_considered": 12,
                "top_genres": [
                    {"genre": "indie rock", "count": 34},
                    {"genre": "alt rock",   "count": 22},
                    {"genre": "post-rock",  "count": 14},
                    {"genre": "dream pop",  "count": 10},
                    {"genre": "shoegaze",   "count": 7},
                    {"genre": "folk rock",  "count": 5},
                ],
                "energy_valence": [
                    {"energy": 0.85, "valence": 0.62, "artist": "Muse",     "title": "Hysteria"},
                    {"energy": 0.40, "valence": 0.30, "artist": "Radiohead", "title": "No Surprises"},
                    {"energy": 0.75, "valence": 0.80, "artist": "Queen",    "title": "Don't Stop Me Now"},
                ] * 10,
                "decades": [
                    {"decade": "1970s", "count": 8},
                    {"decade": "1990s", "count": 21},
                    {"decade": "2000s", "count": 25},
                    {"decade": "2010s", "count": 15},
                ],
            }),
        ))
        page.reload()
        page.wait_for_load_state("networkidle")
        page.locator(".taste-dashboard-section .accordion-header").click()
        page.wait_for_timeout(500)
        _shot_element(page, "75_taste_dashboard", ".taste-dashboard-section")

    def test_76_taste_dashboard_empty(self, page: Page, screenshot_url):
        """Screenshot: dashboard empty state (< 10 tracks)."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.route("**/api/taste/aggregate", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"tracks_considered": 3, "runs_considered": 1,
                             "top_genres": [], "energy_valence": [], "decades": []}),
        ))
        page.reload()
        page.wait_for_load_state("networkidle")
        page.locator(".taste-dashboard-section .accordion-header").click()
        page.wait_for_timeout(300)
        _shot_element(page, "76_taste_dashboard_empty", ".taste-dashboard-section")

    def test_77_tip_toast_first_generation(self, page: Page, screenshot_url):
        """Screenshot: tip toast (first generation complete)."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.evaluate("""() => {
            import('/static/js/modules/tips.js').then(Tips => {
                Tips.showTipById('first_generation_complete');
            });
        }""")
        page.wait_for_timeout(500)
        _shot_element(page, "77_tip_toast_first_generation", ".toast--tip")

    def test_78_tip_toast_disliked(self, page: Page, screenshot_url):
        """Screenshot: tip toast (disliked 2+ tracks)."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.evaluate("""() => {
            import('/static/js/modules/tips.js').then(Tips => {
                Tips.showTipById('disliked_2_plus');
            });
        }""")
        page.wait_for_timeout(500)
        _shot_element(page, "78_tip_toast_disliked", ".toast--tip")

    def test_79_reset_tips_menu(self, page: Page, screenshot_url):
        """Screenshot: burger menu with 'Reset tips' entry visible."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
        page.wait_for_timeout(300)
        _shot_element(page, "79_reset_tips_menu", ".header-controls")

    def test_80_onboarding_step5_card1_enabled(self, page: Page, screenshot_url):
        """Screenshot: onboarding step 5 with card 1 enabled (Wave-3 state)."""
        self._goto_onboarding_page(page, screenshot_url, page_index=4)
        _shot(page, "80_onboarding_step5_card1_enabled")

    # -- Wave 4: Power users ----------------------------------------------

    def test_81_provider_dropdown_expanded(self, page: Page, screenshot_url):
        """Screenshot: Settings modal with provider dropdown open."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
        page.wait_for_timeout(200)
        page.locator("button:has-text('Settings')").click()
        page.wait_for_timeout(300)
        page.locator("#settings-provider").click()
        page.wait_for_timeout(200)
        _shot_element(page, "81_provider_dropdown_expanded", "#settingsModal .modal")

    def test_82_provider_custom_selected(self, page: Page, screenshot_url):
        """Screenshot: Settings modal with Custom provider selected, base URL row visible."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
        page.wait_for_timeout(200)
        page.locator("button:has-text('Settings')").click()
        page.wait_for_timeout(300)
        page.select_option("#settings-provider", "custom")
        page.wait_for_timeout(300)
        _shot_element(page, "82_provider_custom_selected", "#settingsModal .modal")

    def test_83_provider_local_ollama(self, page: Page, screenshot_url):
        """Screenshot: Settings modal with Ollama selected, local notice visible."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
        page.wait_for_timeout(200)
        page.locator("button:has-text('Settings')").click()
        page.wait_for_timeout(300)
        page.select_option("#settings-provider", "ollama")
        page.wait_for_timeout(300)
        _shot_element(page, "83_provider_local_ollama", "#settingsModal .modal")

    def test_84_fetch_models_success(self, page: Page, screenshot_url):
        """Screenshot: Fetch-models successful (populated dropdown)."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.route("**/api/llm/fetch_models", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"]}),
        ))
        page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
        page.wait_for_timeout(200)
        page.locator("button:has-text('Settings')").click()
        page.wait_for_timeout(300)
        page.locator("#btnFetchModels").click()
        page.wait_for_timeout(500)
        _shot_element(page, "84_fetch_models_success", "#settingsModal .modal")

    def test_85_fetch_models_failure(self, page: Page, screenshot_url):
        """Screenshot: Fetch-models with error message inline."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.route("**/api/llm/fetch_models", lambda route: route.fulfill(
            status=502,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"error": "unreachable"}),
        ))
        page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
        page.wait_for_timeout(200)
        page.locator("button:has-text('Settings')").click()
        page.wait_for_timeout(300)
        page.select_option("#settings-provider", "custom")
        page.locator("#settings-base-url").fill("http://unreachable.example/v1")
        page.locator("#btnFetchModels").click()
        page.wait_for_timeout(500)
        _shot_element(page, "85_fetch_models_failure", "#settingsModal .modal")

    def test_86_cost_estimate_full_card(self, page: Page, screenshot_url):
        """Screenshot: Full cost-estimate card in Settings modal (gpt-4.1-mini)."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
        page.wait_for_timeout(200)
        page.locator("button:has-text('Settings')").click()
        page.wait_for_timeout(400)
        _shot_element(page, "86_cost_estimate_full_card", "#costEstimateCard")

    def test_87_cost_estimate_unavailable(self, page: Page, screenshot_url):
        """Screenshot: Cost estimate showing unavailable state for an unknown model."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
        page.wait_for_timeout(200)
        page.locator("button:has-text('Settings')").click()
        page.wait_for_timeout(300)
        page.evaluate("""() => {
            document.getElementById('btnModelMode').click();
            document.getElementById('settings-model-freetext').value = 'llama3.1:8b';
            document.getElementById('settings-model-freetext').dispatchEvent(new Event('input'));
        }""")
        page.wait_for_timeout(400)
        _shot_element(page, "87_cost_estimate_unavailable", "#costEstimateCard")

    def test_88_cost_footnote_generate(self, page: Page, screenshot_url):
        """Screenshot: Generate panel with cost-estimate footnote below the button."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(400)
        _shot_element(page, "88_cost_footnote_generate", "#generateSection .run-section")

    def test_89_onboarding_step6_cost(self, page: Page, screenshot_url):
        """Screenshot: Onboarding step 6 with the Wave-4 cost widget live."""
        self._goto_onboarding_page(page, screenshot_url, page_index=5)
        page.wait_for_timeout(400)
        _shot(page, "89_onboarding_step6_cost")

    def test_90_onboarding_step6_provider_expanded(self, page: Page, screenshot_url):
        """Screenshot: Onboarding step 2 with provider dropdown expanded."""
        self._goto_onboarding_page(page, screenshot_url, page_index=1)
        # Open the custom provider dropdown
        page.locator("#ob-provider-trigger").click()
        page.wait_for_timeout(300)
        _shot(page, "90_onboarding_step6_provider_expanded")

    def test_91_voice_button_idle(self, page: Page, screenshot_url):
        """Screenshot: Voice button in idle state inside the Vibe accordion."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator("#trainToggleBtn").click()
        page.wait_for_timeout(300)
        page.evaluate("document.getElementById('voiceBtnVibe').classList.remove('hidden')")
        page.wait_for_timeout(200)
        _shot_element(page, "91_voice_button_idle", "#accVibeDesc .vibe-textarea-wrap")

    def test_92_voice_button_recording(self, page: Page, screenshot_url):
        """Screenshot: Voice button in recording state."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator("#trainToggleBtn").click()
        page.wait_for_timeout(300)
        page.evaluate("""() => {
            const btn = document.getElementById('voiceBtnVibe');
            btn.classList.remove('hidden');
            btn.classList.add('voice-btn--recording');
            btn.setAttribute('aria-pressed', 'true');
        }""")
        page.wait_for_timeout(200)
        _shot_element(page, "92_voice_button_recording", "#accVibeDesc .vibe-textarea-wrap")

    # -- Wave 5: Polish ---------------------------------------------------

    def test_93_help_modal_en(self, page: Page, screenshot_url):
        """Screenshot: Help modal in English."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
        page.wait_for_timeout(200)
        page.locator("button:has-text('Help')").click()
        page.wait_for_timeout(500)
        _shot_element(page, "93_help_modal_en", "#helpModal .modal")

    def test_94_help_modal_de(self, page: Page, screenshot_url):
        """Screenshot: Help modal served in German (DE file present)."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.evaluate("localStorage.setItem('svLang', 'de')")
        page.reload()
        page.wait_for_load_state("networkidle")
        page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
        page.wait_for_timeout(200)
        page.locator("button:has-text('Hilfe'), button:has-text('Help')").first.click()
        page.wait_for_timeout(500)
        _shot_element(page, "94_help_modal_de", "#helpModal .modal")

    def test_95_help_fallback_banner(self, page: Page, screenshot_url):
        """Screenshot: Help modal with fallback banner visible (simulated)."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        def handle(route):
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({
                    "html": "<h2>About SpotyVibe</h2><p>...</p>",
                    "requested_lang": "de",
                    "served_lang": "en",
                    "fallback_used": True,
                }),
            )
        page.route("**/api/help", handle)
        page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
        page.wait_for_timeout(200)
        page.locator("button:has-text('Help'), button:has-text('Hilfe')").first.click()
        page.wait_for_timeout(500)
        _shot_element(page, "95_help_fallback_banner", "#helpModal .modal")

    def test_96_guide_python_macos_overlay(self, page: Page, screenshot_url):
        """Screenshot: Python-install-macOS guide overlay (English)."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.evaluate("""() => {
            import('/static/js/modules/setup_guide.js').then(SG => {
                SG.openSetupGuide('python_install_macos');
            });
        }""")
        page.wait_for_timeout(700)
        _shot(page, "96_guide_python_macos_overlay")

    def test_97_guide_python_linux_overlay(self, page: Page, screenshot_url):
        """Screenshot: Python-install-Linux guide overlay (English)."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.evaluate("""() => {
            import('/static/js/modules/setup_guide.js').then(SG => {
                SG.openSetupGuide('python_install_linux');
            });
        }""")
        page.wait_for_timeout(700)
        _shot(page, "97_guide_python_linux_overlay")

    def test_98_guide_openai_overlay_de(self, page: Page, screenshot_url):
        """Screenshot: OpenAI setup guide overlay in German."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.evaluate("localStorage.setItem('svLang', 'de')")
        page.reload()
        page.wait_for_load_state("networkidle")
        page.evaluate("""() => {
            import('/static/js/modules/setup_guide.js').then(SG => {
                SG.openSetupGuide('openai_api_key');
            });
        }""")
        page.wait_for_timeout(700)
        _shot(page, "98_guide_openai_overlay_de")

    def test_99_guide_spotify_overlay_de(self, page: Page, screenshot_url):
        """Screenshot: Spotify setup guide overlay in German."""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.evaluate("localStorage.setItem('svLang', 'de')")
        page.reload()
        page.wait_for_load_state("networkidle")
        page.evaluate("""() => {
            import('/static/js/modules/setup_guide.js').then(SG => {
                SG.openSetupGuide('spotify_developer_app');
            });
        }""")
        page.wait_for_timeout(700)
        _shot(page, "99_guide_spotify_overlay_de")

