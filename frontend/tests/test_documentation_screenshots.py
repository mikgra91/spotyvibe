"""Automated screenshot acquisition for documentation/help.md.

Launches the app with mocked APIs, navigates to each section described in
help.md, and captures a screenshot into documentation/assets/screenshots/.

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
    """Capture screenshots for every placeholder in documentation/help.md.

    Each test method corresponds to one or more > **Screenshot placeholder:**
    entries in help.md. Screenshots are saved to:
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
        """Screenshot: Profiles accordion with dropdown and create input"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        page.locator("#trainToggleBtn").click()
        page.wait_for_timeout(600)
        _shot_element(page, "09_profiles_accordion", "#accProfiles")

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
        _shot_element(page, "17_profile_io_controls", "#accProfiles")

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
        _shot_element(page, "20_playlist_mode_selector", ".playlist-mode-row")

    def test_21_audio_filters(self, page: Page, screenshot_url):
        """Screenshot: Audio Filters sub-panel inside Discover Music"""
        page.goto(screenshot_url)
        page.wait_for_load_state("networkidle")
        _switch_tab(page, "spotify")
        page.locator("#generateToggleBtn").click()
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
    # The onboarding flow has 7 steps. `help.md` links to
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
        because documentation/help.md links to it)."""
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
    # (kept at that number because `documentation/help.md` links to it).

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
        page.locator(".ob-cred-guide-toggle").click()
        page.wait_for_timeout(250)
        _shot(page, "51_onboarding_howto_openai_expanded")

    def test_52_setup_guide_openai_overlay(self, page: Page, screenshot_url):
        """Screenshot: The full-screen OpenAI setup guide overlay."""
        self._goto_onboarding_page(page, screenshot_url, page_index=1)
        page.locator(".ob-cred-guide-toggle").click()
        page.wait_for_timeout(250)
        page.locator(".ob-cred-guide-readmore").click()
        page.wait_for_timeout(400)
        _shot(page, "52_setup_guide_openai")

    def test_53_setup_guide_spotify_overlay(self, page: Page, screenshot_url):
        """Screenshot: The full-screen Spotify setup guide overlay."""
        self._goto_onboarding_page(page, screenshot_url, page_index=2)
        page.locator(".ob-cred-guide-toggle").click()
        page.wait_for_timeout(250)
        page.locator(".ob-cred-guide-readmore").click()
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



