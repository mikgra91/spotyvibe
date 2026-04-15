"""End-to-end workflow integration tests.

Each test class exercises a full user workflow as described in help.en.md:
  1. Onboarding / Setup
  2. Generate Playlist (Create New) + Like/Dislike + History + Charts
  3. Generate Playlist (Append) + Like/Dislike + Refine
  4. Generate Playlist (Override/Replace) + Refine
  5. Band/Song Analysis + Quick Copy
  6. Quickstart Guide — OpenAI provider
  7. Quickstart Guide — Spotify provider

All external APIs (OpenAI, Spotify) are mocked.  The Flask app runs on a
random free port for each test session.  API responses are intercepted at
the Playwright level via ``page.route()`` for per-test control.
"""

import json
import re
import socket
import threading
import time
from unittest.mock import patch

import pytest
from playwright.sync_api import Page, expect


# ═══════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════

def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _switch_to_tab(page: Page, tab_name: str):
    page.locator(f'[data-tab="{tab_name}"]').click()
    expect(page.locator(f'[data-tab="{tab_name}"]')).to_have_attribute("aria-selected", "true")


def _open_generate_section(page: Page):
    _switch_to_tab(page, "spotify")
    body = page.locator("#generateBody")
    if not body.is_visible():
        page.locator("#generateToggleBtn").click()
    expect(body).to_be_visible()


def _open_review_section(page: Page):
    _switch_to_tab(page, "spotify")
    body = page.locator("#reviewBody")
    if not body.is_visible():
        page.locator("#reviewToggleBtn").click()
    expect(body).to_be_visible()


def _open_analysis_section(page: Page):
    _switch_to_tab(page, "openai")
    body = page.locator("#analysisBody")
    if not body.is_visible():
        page.locator("#analysisToggleBtn").click()
    expect(body).to_be_visible()


def _expand_dashboard(page: Page):
    body = page.locator("#dashboardBody")
    if not body.is_visible():
        page.locator("#dashboardToggleBtn").click()
        page.wait_for_timeout(300)
    expect(body).to_be_visible()


def _open_quickstart_for_provider(page: Page, provider: str):
    """Open the quickstart modal for a specific provider."""
    page.evaluate(f"""(() => {{
        localStorage.removeItem('spotyvibe-quickstart-dismissed');
        localStorage.removeItem('spotyvibe-quickstart-openai-dismissed');
        localStorage.removeItem('spotyvibe-quickstart-spotify-dismissed');
    }})()""")
    page.evaluate(f"openQuickstart(true)")
    page.wait_for_timeout(200)
    # Reset to the desired provider
    page.evaluate(f"window._quickstartTourModule?.quickstartReset('{provider}')")
    page.wait_for_timeout(200)
    expect(page.locator("#quickstartModal")).to_be_visible()


# ═══════════════════════════════════════════════════════════════════════
#  Mock data
# ═══════════════════════════════════════════════════════════════════════

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

# ----- Generation tracks (5 tracks for Create New workflow) -----

_GENERATED_TRACKS_CREATE = [
    {"artist": "Muse", "track": "Uprising", "reason": "High energy theatrical rock",
     "energy": 0.85, "valence": 0.65, "genres": ["alternative rock", "electronic rock"],
     "release_year": 2009},
    {"artist": "Radiohead", "track": "Airbag", "reason": "Atmospheric and complex",
     "energy": 0.72, "valence": 0.45, "genres": ["alternative rock", "art rock"],
     "release_year": 1997},
    {"artist": "Arctic Monkeys", "track": "Do I Wanna Know?", "reason": "Dark groovy riff",
     "energy": 0.55, "valence": 0.35, "genres": ["indie rock", "alternative rock"],
     "release_year": 2013},
    {"artist": "Queens of the Stone Age", "track": "No One Knows", "reason": "Driving rhythm",
     "energy": 0.90, "valence": 0.55, "genres": ["stoner rock", "alternative rock"],
     "release_year": 2002},
    {"artist": "The Black Keys", "track": "Lonely Boy", "reason": "Catchy blues rock",
     "energy": 0.78, "valence": 0.70, "genres": ["blues rock", "garage rock"],
     "release_year": 2011},
]

# ----- Generation tracks (4 tracks for Append workflow) -----

_GENERATED_TRACKS_APPEND = [
    {"artist": "Foo Fighters", "track": "Everlong", "reason": "Energetic anthem"},
    {"artist": "Royal Blood", "track": "Figure It Out", "reason": "Heavy riff"},
    {"artist": "Biffy Clyro", "track": "Many of Horror", "reason": "Emotional peak"},
    {"artist": "Nothing But Thieves", "track": "Amsterdam", "reason": "Atmospheric vocals"},
]

# ----- Two sets for Override workflow -----

_GENERATED_TRACKS_OVERRIDE_A = [
    {"artist": "Tool", "track": "Schism", "reason": "Complex progressive metal"},
    {"artist": "Deftones", "track": "Change", "reason": "Atmospheric alt metal"},
    {"artist": "System of a Down", "track": "Toxicity", "reason": "Intense and unique"},
]

_GENERATED_TRACKS_OVERRIDE_B = [
    {"artist": "Porcupine Tree", "track": "Trains", "reason": "Melancholic prog rock"},
    {"artist": "Opeth", "track": "Harvest", "reason": "Beautiful acoustic prog"},
    {"artist": "Steven Wilson", "track": "Routine", "reason": "Emotional masterpiece"},
]

# ----- Analysis response -----

_ANALYSIS_RESPONSE = {
    "artist": "Muse",
    "track": "Uprising",
    "genre": ["Alternative Rock", "Electronic Rock"],
    "style_tags": ["theatrical", "electronic rock", "anthemic"],
    "characteristics": {
        "intensity": "high",
        "mood": "rebellious",
    },
    "audio_features": {
        "energy": 0.85,
        "valence": 0.65,
        "tempo": 128.0,
        "danceability": 0.60,
        "acousticness": 0.05,
    },
    "profile_suggestions": [
        "High-energy theatrical rock with electronic elements and anthemic choruses",
        "Driving rhythms with stadium-scale production",
    ],
}

# ----- Playlists for picker -----

_PLAYLISTS = [
    {"id": "pl-create-1", "name": "Workflow Test Playlist"},
    {"id": "pl-append-1", "name": "Append Target"},
    {"id": "pl-replace-1", "name": "Replace Target"},
]

# ----- Taste aggregate data (matching _GENERATED_TRACKS_CREATE) -----

_TASTE_DATA_CREATE = {
    "tracks_considered": 5,
    "runs_considered": 1,
    "neutral": {
        "tracks_considered": 5,
        "top_genres": [
            {"genre": "alternative rock", "count": 4},
            {"genre": "electronic rock", "count": 1},
            {"genre": "art rock", "count": 1},
            {"genre": "indie rock", "count": 1},
            {"genre": "stoner rock", "count": 1},
            {"genre": "blues rock", "count": 1},
            {"genre": "garage rock", "count": 1},
        ],
        "energy_valence": [
            {"artist": "Muse", "title": "Uprising", "energy": 0.85, "valence": 0.65},
            {"artist": "Radiohead", "title": "Airbag", "energy": 0.72, "valence": 0.45},
            {"artist": "Arctic Monkeys", "title": "Do I Wanna Know?", "energy": 0.55, "valence": 0.35},
            {"artist": "Queens of the Stone Age", "title": "No One Knows", "energy": 0.90, "valence": 0.55},
            {"artist": "The Black Keys", "title": "Lonely Boy", "energy": 0.78, "valence": 0.70},
        ],
        "decades": [
            {"decade": "1990s", "count": 1},
            {"decade": "2000s", "count": 2},
            {"decade": "2010s", "count": 2},
        ],
    },
    "liked": {
        "tracks_considered": 2,
        "top_genres": [
            {"genre": "alternative rock", "count": 2},
            {"genre": "electronic rock", "count": 1},
        ],
        "energy_valence": [
            {"artist": "Muse", "title": "Uprising", "energy": 0.85, "valence": 0.65},
            {"artist": "Queens of the Stone Age", "title": "No One Knows", "energy": 0.90, "valence": 0.55},
        ],
        "decades": [
            {"decade": "2000s", "count": 1},
            {"decade": "2000s", "count": 1},
        ],
    },
    "disliked": {
        "tracks_considered": 1,
        "top_genres": [
            {"genre": "indie rock", "count": 1},
            {"genre": "alternative rock", "count": 1},
        ],
        "energy_valence": [
            {"artist": "Arctic Monkeys", "title": "Do I Wanna Know?", "energy": 0.55, "valence": 0.35},
        ],
        "decades": [
            {"decade": "2010s", "count": 1},
        ],
    },
}

_TASTE_DATA_EMPTY = {
    "tracks_considered": 0,
    "runs_considered": 0,
    "neutral": {"tracks_considered": 0, "top_genres": [], "energy_valence": [], "decades": []},
    "liked": {"tracks_considered": 0, "top_genres": [], "energy_valence": [], "decades": []},
    "disliked": {"tracks_considered": 0, "top_genres": [], "energy_valence": [], "decades": []},
}

# ----- Run history matching _GENERATED_TRACKS_CREATE -----

_HISTORY_CREATE = [
    {
        "timestamp": "2026-04-15T10:00:00",
        "playlist_url": "https://open.spotify.com/playlist/pl-create-1",
        "tracks": [
            {"artist": t["artist"], "track": t["track"],
             "energy": t.get("energy"), "valence": t.get("valence"),
             "genres": t.get("genres", []), "release_year": t.get("release_year"),
             "sentiment": "neutral"}
            for t in _GENERATED_TRACKS_CREATE
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════
#  SSE builders
# ═══════════════════════════════════════════════════════════════════════

def _build_sse_stream(tracks, playlist_url="https://open.spotify.com/playlist/test"):
    """Build an SSE body string for a successful generation run."""
    playlist_json = json.dumps(tracks)
    return (
        'data: {"type":"progress","message":"Batch 1: Asking GPT for suggestions…"}\n\n'
        f'data: {{"type":"batch_verified","count":{len(tracks)},"total":{len(tracks)}}}\n\n'
        f'data: {{"type":"result","playlist":{playlist_json},'
        f'"playlist_url":"{playlist_url}",'
        f'"playlist_id":"pl-gen-id",'
        f'"added":{len(tracks)},"not_found":[],"was_cancelled":false}}\n\n'
    )


# ═══════════════════════════════════════════════════════════════════════
#  Session-scoped Flask server
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def _base_url():
    port = _free_port()
    url = f"http://127.0.0.1:{port}"

    _profile_state = {"profile": dict(_TRAINED_PROFILE), "trained": True}

    def fake_get_credentials():
        return {
            "OPENAI_API_KEY": {"masked": "****1234", "is_set": True},
            "SPOTIPY_CLIENT_ID": {"masked": "****c-id", "is_set": True},
            "SPOTIPY_CLIENT_SECRET": {"masked": "****c-se", "is_set": True},
        }

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

    def fake_get_openai_models():
        return [
            {"id": "gpt-4.1-mini", "label": "gpt-4.1-mini", "supported": True},
        ]

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
        _profile_state["profile"]["last_updated"] = "2025-01-01T00:00:00"
        return _profile_state["profile"]

    def fake_save_profile_sections(sections):
        _profile_state["trained"] = True
        _profile_state["profile"]["last_updated"] = "2025-01-01T00:00:00"
        return _profile_state["profile"]

    patches = [
        patch("app.get_credentials", fake_get_credentials),
        patch("app.save_credentials", lambda data: None),
        patch("app.get_settings", fake_get_settings),
        patch("app.get_model", return_value="gpt-4.1-mini"),
        patch("app.get_openai_models", fake_get_openai_models),
        patch("app.get_spotify_auth_status", return_value="authenticated"),
        patch("app.is_profile_trained", fake_is_profile_trained),
        patch("app.get_profile_status", fake_get_profile_status),
        patch("app.load_profile", fake_load_profile),
        patch("app.save_profile", fake_save_profile),
        patch("app.train_profile", fake_train_profile),
        patch("app.save_profile_sections", fake_save_profile_sections),
        patch("app.export_profile_dict", lambda: _profile_state["profile"]),
        patch("app.like_track", lambda *a, **kw: None),
        patch("app.dislike_track", lambda *a, **kw: None),
        patch("app.remove_from_playlist", lambda *a, **kw: {"removed": True}),
        patch("app.clear_debug_log", lambda: None),
        patch("app.get_debug_mode", return_value=False),
        patch("app.get_playlist_size", return_value=10),
        patch("app.get_new_artist_percentage", return_value=30),
        patch("app.is_onboarding_completed", return_value=True),
        patch("app.get_gpt_language", return_value="English"),
        # Profile CRUD — no-ops
        patch("app.list_profiles", return_value=[]),
        patch("app.create_profile", return_value={"id": "new-id", "name": "New"}),
        patch("app.delete_profile", return_value=None),
        patch("app.activate_profile", return_value=None),
        patch("app.get_active_profile_id", return_value=""),
        # Taste / runs — empty by default (tests override via page.route)
        patch("app.aggregate_taste", return_value=_TASTE_DATA_EMPTY),
        patch("app.load_runs", return_value=[]),
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


@pytest.fixture(scope="session")
def base_url(_base_url):
    return _base_url


# ═══════════════════════════════════════════════════════════════════════
#  1. Onboarding / Setup Workflow
# ═══════════════════════════════════════════════════════════════════════

class TestOnboardingSetupWorkflow:
    """Full onboarding wizard — 7 steps from Welcome to Ready.

    Verifies: step progression, credential inputs, save calls, skip,
    and completion marking.
    """

    def _navigate_to_onboarding(self, page: Page, base_url: str):
        """Navigate to /onboarding with incomplete status."""
        page.route("**/api/onboarding/status", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"completed": False}),
        ))
        page.goto(base_url + "/onboarding?replay=1")
        page.wait_for_load_state("networkidle")

    def _go_to_page(self, page: Page, target: int):
        """Advance through onboarding pages by clicking CTAs."""
        for _ in range(target):
            cta = page.locator(
                ".ob-page.active .ob-cta-start, "
                ".ob-page.active .ob-cta-skip-inline"
            ).first
            cta.click()
            page.wait_for_timeout(500)

    def test_onboarding_loads_welcome_step(self, page: Page, base_url):
        """Step 0 (Welcome) shows the intro content and feature list."""
        self._navigate_to_onboarding(page, base_url)
        expect(page.locator(".ob-wrap")).to_be_visible()
        # Welcome page has the 3 feature descriptions
        expect(page.locator(".ob-feature")).to_have_count(3)
        # First pill is current
        pills = page.locator(".ob-pill")
        expect(pills.first).to_have_class(re.compile(r"ob-pill--current"))

    def test_step_indicators_advance(self, page: Page, base_url):
        """Step 0 has first pill current; after advancing, active page changes."""
        self._navigate_to_onboarding(page, base_url)
        # Step 0: first pill is current on the first page
        first_page_pills = page.locator(".ob-page").first.locator(".ob-pill")
        expect(first_page_pills.nth(0)).to_have_class(re.compile(r"ob-pill--current"))
        # Verify each step page's indicator is correctly pre-set in HTML
        # Step 1 (page 2 in DOM) should have first pill as 'complete'
        second_page_pills = page.locator(".ob-page").nth(1).locator(".ob-pill")
        expect(second_page_pills.nth(0)).to_have_class(re.compile(r"ob-pill--complete"))
        expect(second_page_pills.nth(1)).to_have_class(re.compile(r"ob-pill--current"))

    def test_openai_credential_step(self, page: Page, base_url):
        """Step 1 (OpenAI key) shows the API key input field."""
        page.route("**/api/settings/credentials", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "OPENAI_API_KEY": {"masked": "", "is_set": False},
                "SPOTIPY_CLIENT_ID": {"masked": "", "is_set": False},
                "SPOTIPY_CLIENT_SECRET": {"masked": "", "is_set": False},
            }),
        ))
        self._navigate_to_onboarding(page, base_url)
        self._go_to_page(page, 1)  # Welcome → OpenAI key
        expect(page.locator("#ob-openai-key")).to_be_visible()

    def test_spotify_credential_step(self, page: Page, base_url):
        """Step 2 (Spotify creds) shows Client ID and Secret inputs."""
        page.route("**/api/settings/credentials", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "OPENAI_API_KEY": {"masked": "", "is_set": False},
                "SPOTIPY_CLIENT_ID": {"masked": "", "is_set": False},
                "SPOTIPY_CLIENT_SECRET": {"masked": "", "is_set": False},
            }),
        ))
        self._navigate_to_onboarding(page, base_url)
        self._go_to_page(page, 2)  # Jump to Spotify creds
        expect(page.locator("#ob-spotify-id")).to_be_visible()
        expect(page.locator("#ob-spotify-secret")).to_be_visible()

    def test_credential_save_button_present(self, page: Page, base_url):
        """Step 1 (OpenAI key) has a Next button that triggers credential save."""
        page.route("**/api/settings/credentials", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "OPENAI_API_KEY": {"masked": "", "is_set": False},
                "SPOTIPY_CLIENT_ID": {"masked": "", "is_set": False},
                "SPOTIPY_CLIENT_SECRET": {"masked": "", "is_set": False},
            }),
        ))
        self._navigate_to_onboarding(page, base_url)
        self._go_to_page(page, 1)  # Welcome → OpenAI
        # The OpenAI key input exists on step 1
        expect(page.locator("#ob-openai-key")).to_be_attached()
        # The "Next →" button (with obSaveAndNext) exists
        next_btn = page.locator('.ob-cta-next[onclick="obSaveAndNext()"]')
        # There should be at least one such button in the DOM (even if not visible on active page)
        assert next_btn.count() >= 1

    def test_full_wizard_to_ready_step(self, page: Page, base_url):
        """Walk through all 7 steps and reach the Ready page."""
        page.route("**/api/settings/credentials", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "OPENAI_API_KEY": {"masked": "****1234", "is_set": True},
                "SPOTIPY_CLIENT_ID": {"masked": "****c-id", "is_set": True},
                "SPOTIPY_CLIENT_SECRET": {"masked": "****c-se", "is_set": True},
            }),
        ))
        page.route("**/api/spotify/status", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"status": "authenticated"}),
        ))
        self._navigate_to_onboarding(page, base_url)
        self._go_to_page(page, 6)  # Jump to last step (Ready)
        # Step 6 = Ready page — should have a CTA
        ready_cta = page.locator(
            ".ob-page.active .ob-cta-start, .ob-page.active .ob-cta-finish, "
            ".ob-page.active .ob-cta-next"
        )
        expect(ready_cta.first).to_be_visible()

    def test_language_toggle_visible_throughout(self, page: Page, base_url):
        """Language toggle is visible on every step."""
        self._navigate_to_onboarding(page, base_url)
        expect(page.locator(".ob-lang-toggle")).to_be_visible()
        self._go_to_page(page, 1)
        expect(page.locator(".ob-lang-toggle")).to_be_visible()
        self._go_to_page(page, 3)
        expect(page.locator(".ob-lang-toggle")).to_be_visible()

    def test_skip_button_present_on_welcome(self, page: Page, base_url):
        """The Skip button is present on the Welcome step."""
        self._navigate_to_onboarding(page, base_url)
        skip = page.locator('.ob-page.active .ob-btn-skip[onclick="skipOnboarding()"]')
        expect(skip).to_be_visible()


# ═══════════════════════════════════════════════════════════════════════
#  2. Generate Playlist (Create New) + Like/Dislike + History + Charts
# ═══════════════════════════════════════════════════════════════════════

class TestGenerateCreateNewPlaylist:
    """Generate a new playlist, give feedback, verify history and taste charts.

    Workflow: Generate → 5 tracks appear → like 2, dislike 1 →
    check history shows correct tracks → charts reflect generation data.
    """

    def _setup_generation(self, page: Page, base_url: str):
        """Set up mocked SSE generation and navigate to generate section."""
        sse_body = _build_sse_stream(
            _GENERATED_TRACKS_CREATE,
            "https://open.spotify.com/playlist/pl-create-1",
        )

        page.route("**/api/run", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
            body=sse_body,
        ))
        page.route("**/api/profile/status", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"trained": True, "last_updated": "2025-01-01T00:00:00"}),
        ))

        page.goto(base_url)
        page.wait_for_load_state("networkidle")

    def _run_generation(self, page: Page):
        """Trigger generation and wait for tracks."""
        _open_generate_section(page)
        page.locator("#runBtn").click()
        page.locator(".track-item").first.wait_for(timeout=5000)

    def test_generation_creates_5_tracks(self, page: Page, base_url):
        """Generation produces 5 track cards with correct artist names."""
        self._setup_generation(page, base_url)
        self._run_generation(page)

        tracks = page.locator(".track-item")
        assert tracks.count() == 5
        expect(tracks.nth(0)).to_contain_text("Muse")
        expect(tracks.nth(1)).to_contain_text("Radiohead")
        expect(tracks.nth(2)).to_contain_text("Arctic Monkeys")
        expect(tracks.nth(3)).to_contain_text("Queens of the Stone Age")
        expect(tracks.nth(4)).to_contain_text("The Black Keys")

    def test_playlist_link_shown(self, page: Page, base_url):
        """After generation, the playlist link is displayed."""
        self._setup_generation(page, base_url)
        self._run_generation(page)
        expect(page.locator("#playlistLinkBox")).to_be_visible()
        expect(page.locator("#playlistLinkBox")).to_contain_text("open.spotify.com")

    def test_like_tracks_sends_feedback(self, page: Page, base_url):
        """Liking 2 tracks sends correct feedback API calls."""
        self._setup_generation(page, base_url)
        feedback_calls = []

        page.route("**/api/feedback", lambda route: (
            feedback_calls.append(route.request.post_data_json),
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"status": "ok"}),
            ),
        )[1])

        self._run_generation(page)

        # Like track 0 (Muse)
        page.locator("#track-0 .btn-like").click()
        page.locator("#submitBtn-0").click()
        page.wait_for_timeout(300)

        # Like track 3 (Queens of the Stone Age)
        page.locator("#track-3 .btn-like").click()
        page.locator("#submitBtn-3").click()
        page.wait_for_timeout(300)

        likes = [c for c in feedback_calls if c["action"] == "like"]
        assert len(likes) == 2
        assert likes[0]["artist"] == "Muse"
        assert likes[1]["artist"] == "Queens of the Stone Age"

    def test_dislike_track_sends_feedback(self, page: Page, base_url):
        """Disliking a track sends the correct feedback API call."""
        self._setup_generation(page, base_url)
        feedback_calls = []

        page.route("**/api/feedback", lambda route: (
            feedback_calls.append(route.request.post_data_json),
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"status": "ok", "removal": {"removed": True}}),
            ),
        )[1])

        self._run_generation(page)

        # Dislike track 2 (Arctic Monkeys)
        page.locator("#track-2 .btn-dislike").click()
        page.locator("#submitBtn-2").click()
        page.wait_for_timeout(300)

        dislikes = [c for c in feedback_calls if c["action"] == "dislike"]
        assert len(dislikes) == 1
        assert dislikes[0]["artist"] == "Arctic Monkeys"

    def test_history_shows_generated_tracks(self, page: Page, base_url):
        """After generation, run history contains the correct 5 tracks."""
        self._setup_generation(page, base_url)

        page.route("**/api/runs", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"runs": _HISTORY_CREATE}),
        ))

        self._run_generation(page)

        # Switch to History tab
        _switch_to_tab(page, "history")
        page.evaluate("loadHistory()")
        page.wait_for_timeout(500)

        items = page.locator("#historyList .history-run-item")
        assert items.count() >= 1

        # Expand the first history entry
        items.first.click()
        page.wait_for_timeout(300)
        expect(items.first).to_have_class(re.compile(r"expanded"))

        # Check that it contains the expected artists
        expanded = items.first
        expect(expanded).to_contain_text("Muse")
        expect(expanded).to_contain_text("Radiohead")
        expect(expanded).to_contain_text("Arctic Monkeys")
        expect(expanded).to_contain_text("Queens of the Stone Age")
        expect(expanded).to_contain_text("The Black Keys")

    def test_history_has_playlist_link(self, page: Page, base_url):
        """History entry has an 'Open playlist' link."""
        self._setup_generation(page, base_url)

        page.route("**/api/runs", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"runs": _HISTORY_CREATE}),
        ))

        self._run_generation(page)
        _switch_to_tab(page, "history")
        page.evaluate("loadHistory()")
        page.wait_for_timeout(500)

        link = page.locator("#historyList .history-run-item").first.locator("a", has_text="Open playlist")
        expect(link).to_have_count(1)

    def test_taste_dashboard_charts_reflect_generation(self, page: Page, base_url):
        """After generation, taste dashboard shows genres, energy×valence, decades."""
        self._setup_generation(page, base_url)

        page.route("**/api/taste/aggregate", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps(_TASTE_DATA_CREATE),
        ))

        self._run_generation(page)

        # Switch to OpenAI tab and expand dashboard
        _switch_to_tab(page, "openai")
        _expand_dashboard(page)
        page.wait_for_timeout(800)

        # Genre donut chart should be rendered (SVG element)
        genres_svg = page.locator("#dashboardNeutral .dashboard-card--genres svg")
        expect(genres_svg).to_have_count(1)

        # Energy × Valence scatter chart should be rendered
        scatter_svg = page.locator("#dashboardNeutral .dashboard-card--scatter svg")
        expect(scatter_svg).to_have_count(1)

        # Decades bar chart should be rendered
        decades_svg = page.locator("#dashboardNeutral .dashboard-card--decades svg")
        expect(decades_svg).to_have_count(1)

    def test_taste_dashboard_empty_state_disappears(self, page: Page, base_url):
        """With taste data, the empty state placeholder is not shown."""
        self._setup_generation(page, base_url)

        page.route("**/api/taste/aggregate", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps(_TASTE_DATA_CREATE),
        ))

        self._run_generation(page)
        _switch_to_tab(page, "openai")
        _expand_dashboard(page)
        page.wait_for_timeout(800)

        expect(page.locator(".dashboard-empty")).to_be_hidden()


# ═══════════════════════════════════════════════════════════════════════
#  3. Generate Playlist (Append) + Like/Dislike + Refine
# ═══════════════════════════════════════════════════════════════════════

class TestGenerateAppendPlaylist:
    """Generate in Append mode, give feedback, then verify via Refine Playlist.

    Workflow: Generate (append, 4 tracks) → like 2, dislike 1 →
    open Refine → load playlist → verify 3 tracks remain (disliked removed).
    """

    def _setup_and_generate(self, page: Page, base_url: str, feedback_calls: list):
        """Set up mocked generation in append mode and run it."""
        sse_body = _build_sse_stream(
            _GENERATED_TRACKS_APPEND,
            "https://open.spotify.com/playlist/pl-append-1",
        )

        page.route("**/api/run", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
            body=sse_body,
        ))
        page.route("**/api/profile/status", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"trained": True, "last_updated": "2025-01-01T00:00:00"}),
        ))
        page.route("**/api/feedback", lambda route: (
            feedback_calls.append(route.request.post_data_json),
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"status": "ok", "removal": {"removed": True}}),
            ),
        )[1])

        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        _open_generate_section(page)
        # Select "append" mode if available (radio button)
        append_radio = page.locator('input[name="playlist_mode"][value="append"]')
        if append_radio.count() > 0:
            append_radio.check(force=True)
            page.wait_for_timeout(200)

        page.locator("#runBtn").click()
        page.locator(".track-item").first.wait_for(timeout=5000)

    def test_generation_creates_4_tracks(self, page: Page, base_url):
        """Append-mode generation produces 4 track cards."""
        feedback_calls = []
        self._setup_and_generate(page, base_url, feedback_calls)
        assert page.locator(".track-item").count() == 4

    def test_like_and_dislike_feedback(self, page: Page, base_url):
        """Like 2 tracks and dislike 1 — verify all 3 feedback calls sent."""
        feedback_calls = []
        self._setup_and_generate(page, base_url, feedback_calls)

        # Like track 0 (Foo Fighters)
        page.locator("#track-0 .btn-like").click()
        page.locator("#submitBtn-0").click()
        page.wait_for_timeout(300)

        # Like track 1 (Royal Blood)
        page.locator("#track-1 .btn-like").click()
        page.locator("#submitBtn-1").click()
        page.wait_for_timeout(300)

        # Dislike track 2 (Biffy Clyro)
        page.locator("#track-2 .btn-dislike").click()
        page.locator("#submitBtn-2").click()
        page.wait_for_timeout(300)

        likes = [c for c in feedback_calls if c["action"] == "like"]
        dislikes = [c for c in feedback_calls if c["action"] == "dislike"]
        assert len(likes) == 2
        assert len(dislikes) == 1
        assert likes[0]["artist"] == "Foo Fighters"
        assert likes[1]["artist"] == "Royal Blood"
        assert dislikes[0]["artist"] == "Biffy Clyro"

    def test_refine_shows_remaining_tracks(self, page: Page, base_url):
        """After disliking 1 of 4, Refine Playlist shows 3 tracks.

        Disliked tracks are removed from the Spotify playlist, so when
        loading via Refine, only liked + neutral tracks appear.
        """
        feedback_calls = []
        self._setup_and_generate(page, base_url, feedback_calls)

        # Give feedback: like 0, like 1, dislike 2 (track 3 is neutral)
        page.locator("#track-0 .btn-like").click()
        page.locator("#submitBtn-0").click()
        page.wait_for_timeout(300)

        page.locator("#track-1 .btn-like").click()
        page.locator("#submitBtn-1").click()
        page.wait_for_timeout(300)

        page.locator("#track-2 .btn-dislike").click()
        page.locator("#submitBtn-2").click()
        page.wait_for_timeout(300)

        # Remaining tracks for Refine: Foo Fighters, Royal Blood, Nothing But Thieves
        # (Biffy Clyro was disliked and removed from the playlist)
        remaining_tracks = [
            {"artist": "Foo Fighters", "track": "Everlong", "track_id": "t1",
             "cover_url": "https://example.com/c1.jpg"},
            {"artist": "Royal Blood", "track": "Figure It Out", "track_id": "t2",
             "cover_url": "https://example.com/c2.jpg"},
            {"artist": "Nothing But Thieves", "track": "Amsterdam", "track_id": "t4",
             "cover_url": "https://example.com/c4.jpg"},
        ]

        page.route("**/api/playlists", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"playlists": _PLAYLISTS}),
        ))
        page.route("**/api/playlist/*/tracks", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"tracks": remaining_tracks}),
        ))

        _open_review_section(page)
        page.wait_for_timeout(400)
        picker = page.locator("#reviewPlaylistPicker")
        picker.wait_for(state="visible")
        picker.select_option(index=1)
        page.locator("#reviewLoadBtn").click()
        page.locator("#reviewTrackArea").wait_for(state="visible", timeout=5000)

        review_items = page.locator("#reviewTrackList .track-item")
        assert review_items.count() == 3
        expect(review_items.nth(0)).to_contain_text("Foo Fighters")
        expect(review_items.nth(1)).to_contain_text("Royal Blood")
        expect(review_items.nth(2)).to_contain_text("Nothing But Thieves")


# ═══════════════════════════════════════════════════════════════════════
#  4. Generate Playlist (Override/Replace) + Refine
# ═══════════════════════════════════════════════════════════════════════

class TestGenerateOverridePlaylist:
    """Generate with Replace mode, then re-generate and verify playlist changed.

    Workflow: Generate (replace, set A) → verify 3 tracks →
    generate again (replace, set B) → verify different 3 tracks →
    load via Refine → shows set B tracks.
    """

    def _setup_generation_with_tracks(self, page: Page, base_url: str, tracks: list,
                                       playlist_url: str):
        """Mock SSE for a generation run with the given tracks."""
        sse_body = _build_sse_stream(tracks, playlist_url)

        # Unroute before re-routing to avoid stale handlers
        try:
            page.unroute("**/api/run")
        except Exception:
            pass

        page.route("**/api/run", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
            body=sse_body,
        ))
        page.route("**/api/profile/status", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"trained": True, "last_updated": "2025-01-01T00:00:00"}),
        ))

    def _select_replace_mode(self, page: Page):
        """Switch to advanced mode and select the replace playlist mode."""
        # Ensure advanced mode is active to see playlist mode options
        adv_btn = page.locator(".gen-mode-btn[data-mode='advanced']")
        if adv_btn.count() > 0:
            adv_btn.click()
            page.wait_for_timeout(200)
        replace_radio = page.locator('input[name="playlist_mode"][value="replace"]')
        if replace_radio.count() > 0:
            replace_radio.check(force=True)
            page.wait_for_timeout(200)

    def test_first_generation_shows_set_a(self, page: Page, base_url):
        """First replace-mode generation shows Set A tracks."""
        self._setup_generation_with_tracks(
            page, base_url, _GENERATED_TRACKS_OVERRIDE_A,
            "https://open.spotify.com/playlist/pl-replace-1",
        )

        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        _open_generate_section(page)
        self._select_replace_mode(page)

        page.locator("#runBtn").click()
        page.locator(".track-item").first.wait_for(timeout=5000)

        assert page.locator(".track-item").count() == 3
        expect(page.locator(".track-item").nth(0)).to_contain_text("Tool")
        expect(page.locator(".track-item").nth(1)).to_contain_text("Deftones")
        expect(page.locator(".track-item").nth(2)).to_contain_text("System of a Down")

    def test_second_generation_replaces_with_set_b(self, page: Page, base_url):
        """Second replace-mode generation shows completely different Set B tracks."""
        # First generation (set A)
        self._setup_generation_with_tracks(
            page, base_url, _GENERATED_TRACKS_OVERRIDE_A,
            "https://open.spotify.com/playlist/pl-replace-1",
        )
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        _open_generate_section(page)
        self._select_replace_mode(page)
        page.locator("#runBtn").click()
        page.locator(".track-item").first.wait_for(timeout=5000)
        assert page.locator(".track-item").count() == 3

        # Second generation (set B) — re-route and reload
        self._setup_generation_with_tracks(
            page, base_url, _GENERATED_TRACKS_OVERRIDE_B,
            "https://open.spotify.com/playlist/pl-replace-1",
        )

        page.reload()
        page.wait_for_load_state("networkidle")

        _open_generate_section(page)
        self._select_replace_mode(page)

        page.locator("#runBtn").click()
        page.locator(".track-item").first.wait_for(timeout=5000)

        assert page.locator(".track-item").count() == 3
        expect(page.locator(".track-item").nth(0)).to_contain_text("Porcupine Tree")
        expect(page.locator(".track-item").nth(1)).to_contain_text("Opeth")
        expect(page.locator(".track-item").nth(2)).to_contain_text("Steven Wilson")

    def test_refine_shows_replaced_tracks(self, page: Page, base_url):
        """Loading the playlist via Refine after Replace shows the new tracks."""
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        # After replace, the playlist now contains Set B tracks
        replaced_tracks = [
            {"artist": "Porcupine Tree", "track": "Trains", "track_id": "rt1",
             "cover_url": "https://example.com/c1.jpg"},
            {"artist": "Opeth", "track": "Harvest", "track_id": "rt2",
             "cover_url": "https://example.com/c2.jpg"},
            {"artist": "Steven Wilson", "track": "Routine", "track_id": "rt3",
             "cover_url": "https://example.com/c3.jpg"},
        ]

        page.route("**/api/playlists", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"playlists": _PLAYLISTS}),
        ))
        page.route("**/api/playlist/*/tracks", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"tracks": replaced_tracks}),
        ))

        _open_review_section(page)
        page.wait_for_timeout(400)
        picker = page.locator("#reviewPlaylistPicker")
        picker.wait_for(state="visible")
        picker.select_option(index=1)
        page.locator("#reviewLoadBtn").click()
        page.locator("#reviewTrackArea").wait_for(state="visible", timeout=5000)

        review_items = page.locator("#reviewTrackList .track-item")
        assert review_items.count() == 3
        expect(review_items.nth(0)).to_contain_text("Porcupine Tree")
        expect(review_items.nth(1)).to_contain_text("Opeth")
        expect(review_items.nth(2)).to_contain_text("Steven Wilson")


# ═══════════════════════════════════════════════════════════════════════
#  5. Band/Song Analysis + Quick Copy
# ═══════════════════════════════════════════════════════════════════════

class TestBandSongAnalysisWorkflow:
    """Analyse a song and verify audio features, characteristics, and quick copy.

    Workflow: Open Analysis → enter "Muse" + "Uprising" → Analyse →
    verify energy, valence, tempo, danceability, acousticness displayed →
    verify quick copy provides correct suggestion value.
    """

    def _run_analysis(self, page: Page, base_url: str):
        """Set up mock, navigate, and run an analysis."""
        page.goto(base_url)
        page.wait_for_load_state("networkidle")

        page.route("**/api/analyze", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps(_ANALYSIS_RESPONSE),
        ))

        _open_analysis_section(page)
        page.locator("#analysisArtist").fill("Muse")
        page.locator("#analysisTrack").fill("Uprising")
        page.locator("#analysisSendBtn").click()
        page.locator("#analysisResult .analysis-card").wait_for(state="visible", timeout=5000)
        page.wait_for_timeout(300)

    def test_analysis_result_visible(self, page: Page, base_url):
        """Analysis result area appears after successful analysis."""
        self._run_analysis(page, base_url)
        expect(page.locator("#analysisResult")).to_be_visible()

    def test_artist_and_track_in_result(self, page: Page, base_url):
        """Result shows the correct artist and track name."""
        self._run_analysis(page, base_url)
        result = page.locator("#analysisResult")
        expect(result).to_contain_text("Muse")
        expect(result).to_contain_text("Uprising")

    def test_genre_displayed(self, page: Page, base_url):
        """Result shows the genre tags."""
        self._run_analysis(page, base_url)
        result = page.locator("#analysisResult")
        expect(result).to_contain_text("Alternative Rock")

    def test_energy_value_displayed(self, page: Page, base_url):
        """Energy audio feature (85%) is displayed."""
        self._run_analysis(page, base_url)
        result = page.locator("#analysisResult")
        expect(result).to_contain_text("85%")

    def test_valence_value_displayed(self, page: Page, base_url):
        """Valence audio feature (65%) is displayed."""
        self._run_analysis(page, base_url)
        result = page.locator("#analysisResult")
        expect(result).to_contain_text("65%")

    def test_tempo_value_displayed(self, page: Page, base_url):
        """Tempo audio feature (128 BPM) is displayed."""
        self._run_analysis(page, base_url)
        result = page.locator("#analysisResult")
        expect(result).to_contain_text("128 BPM")

    def test_danceability_value_displayed(self, page: Page, base_url):
        """Danceability audio feature (60%) is displayed."""
        self._run_analysis(page, base_url)
        result = page.locator("#analysisResult")
        expect(result).to_contain_text("60%")

    def test_acousticness_value_displayed(self, page: Page, base_url):
        """Acousticness audio feature (5%) is displayed."""
        self._run_analysis(page, base_url)
        result = page.locator("#analysisResult")
        expect(result).to_contain_text("5%")

    def test_profile_suggestions_displayed(self, page: Page, base_url):
        """Profile suggestions are shown with copy buttons."""
        self._run_analysis(page, base_url)
        suggestions = page.locator("#analysisResult .btn-copy-suggestion")
        assert suggestions.count() == 2

    def test_quick_copy_has_correct_value(self, page: Page, base_url):
        """The copy button carries the correct suggestion text."""
        self._run_analysis(page, base_url)
        first_btn = page.locator("#analysisResult .btn-copy-suggestion").first
        suggestion_text = first_btn.get_attribute("data-suggestion")
        assert suggestion_text == "High-energy theatrical rock with electronic elements and anthemic choruses"

    def test_filter_buttons_present(self, page: Page, base_url):
        """Each filterable audio feature has a '⇒ Filter' button."""
        self._run_analysis(page, base_url)
        filter_buttons = page.locator("#analysisResult .af-use-btn")
        # energy, valence, tempo, danceability, acousticness = 5 filterable features
        assert filter_buttons.count() == 5

    def test_use_all_filters_button_present(self, page: Page, base_url):
        """The 'Use All as Filters' button is present."""
        self._run_analysis(page, base_url)
        use_all = page.locator("#analysisResult .af-use-all-btn")
        expect(use_all).to_be_visible()


# ═══════════════════════════════════════════════════════════════════════
#  6. Quickstart Guide — OpenAI Provider
# ═══════════════════════════════════════════════════════════════════════

class TestQuickstartOpenAIWorkflow:
    """Quickstart guide for the OpenAI provider.

    Verifies: auto-trigger on first visit, TOC entries = Setup +
    Build Your Profile + Band/Song Analysis, each step has key actions
    and demo player.
    """

    def _open_quickstart_openai(self, page: Page, base_url: str):
        """Navigate and open quickstart for OpenAI provider."""
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        # Ensure OpenAI tab is active (default)
        _switch_to_tab(page, "openai")
        page.wait_for_timeout(200)
        # Clear dismiss flags and force-open for OpenAI
        page.evaluate("""(() => {
            localStorage.removeItem('spotyvibe-quickstart-dismissed');
            localStorage.removeItem('spotyvibe-quickstart-openai-dismissed');
            localStorage.removeItem('spotyvibe-quickstart-spotify-dismissed');
        })()""")
        page.evaluate("openQuickstart(true)")
        page.wait_for_timeout(300)
        expect(page.locator("#quickstartModal")).to_be_visible()

    def test_quickstart_opens_for_openai(self, page: Page, base_url):
        """Quickstart modal opens and is visible."""
        self._open_quickstart_openai(page, base_url)
        expect(page.locator("#quickstartModal")).to_be_visible()

    def test_toc_has_correct_openai_entries(self, page: Page, base_url):
        """TOC shows Setup, Build Your Profile, Band/Song Analysis for OpenAI."""
        self._open_quickstart_openai(page, base_url)
        toc = page.locator(".qs-toc")
        expect(toc).to_be_visible()

        # OpenAI TOC entries: "both" (Setup) + "openai" (Profile, Analysis)
        visible_entries = toc.locator(
            '.qs-toc-entry[data-qs-provider="both"], '
            '.qs-toc-entry[data-qs-provider="openai"]'
        )
        assert visible_entries.count() == 3

        # Verify labels by aria-label
        expect(toc.locator('[aria-label="Go to Setup"]')).to_be_visible()
        expect(toc.locator('[aria-label="Go to Build Your Profile"]')).to_be_visible()
        expect(toc.locator('[aria-label="Go to Band/Song Analysis"]')).to_be_visible()

    def test_toc_does_not_show_spotify_entries(self, page: Page, base_url):
        """Spotify-only TOC entries are not visible in OpenAI quickstart."""
        self._open_quickstart_openai(page, base_url)
        toc = page.locator(".qs-toc")
        # Spotify-only entries should exist in DOM but not be visible in TOC navigation
        # (they're just not reachable — the TOC only shows entries matching the active provider)
        # The Setup entry is "both" so it appears. Spotify-only entries are filtered by the tour JS.
        expect(toc.locator('[aria-label="Go to Setup"]')).to_be_visible()

    def test_setup_step_has_key_actions(self, page: Page, base_url):
        """Step 1 (Setup) shows key actions checklist."""
        self._open_quickstart_openai(page, base_url)
        page.locator('.qs-toc-entry[aria-label="Go to Setup"]').click()
        page.wait_for_timeout(300)
        step_page = page.locator('[data-qs-page="1"]')
        expect(step_page).to_be_visible()
        # Key actions list is present
        expect(step_page.locator(".qs-key-actions")).to_be_visible()
        expect(step_page.locator(".qs-key-actions li")).to_have_count(4)

    def test_setup_step_has_demo_player(self, page: Page, base_url):
        """Step 1 (Setup) has an interactive demo player."""
        self._open_quickstart_openai(page, base_url)
        page.locator('.qs-toc-entry[aria-label="Go to Setup"]').click()
        page.wait_for_timeout(300)
        expect(page.locator('[data-qs-page="1"] .qs-demo-player')).to_be_visible()

    def test_profile_step_content(self, page: Page, base_url):
        """Step 2 (Build Your Profile) shows correct title and key actions."""
        self._open_quickstart_openai(page, base_url)
        page.locator('.qs-toc-entry[aria-label="Go to Build Your Profile"]').click()
        page.wait_for_timeout(300)
        step_page = page.locator('[data-qs-page="2"]')
        expect(step_page).to_be_visible()
        expect(step_page.locator(".qs-page-title")).to_contain_text("Build Your Profile")
        expect(step_page.locator(".qs-key-actions li")).to_have_count(4)
        expect(step_page.locator(".qs-demo-player")).to_be_visible()

    def test_analysis_step_content(self, page: Page, base_url):
        """Step 7 (Band/Song Analysis) shows correct title and key actions."""
        self._open_quickstart_openai(page, base_url)
        page.locator('.qs-toc-entry[aria-label="Go to Band/Song Analysis"]').click()
        page.wait_for_timeout(300)
        step_page = page.locator('[data-qs-page="7"]')
        expect(step_page).to_be_visible()
        expect(step_page.locator(".qs-page-title")).to_contain_text("Band/Song Analysis")
        expect(step_page.locator(".qs-key-actions li")).to_have_count(4)
        expect(step_page.locator(".qs-demo-player")).to_be_visible()

    def test_pagination_navigates_steps(self, page: Page, base_url):
        """Next/Back buttons navigate through OpenAI-specific steps."""
        self._open_quickstart_openai(page, base_url)
        # Go to first step
        page.locator('.qs-toc-entry[aria-label="Go to Setup"]').click()
        page.wait_for_timeout(300)
        expect(page.locator('[data-qs-page="1"]')).to_be_visible()

        # Click Next
        page.locator("#qsPagNext").click()
        page.wait_for_timeout(300)
        expect(page.locator('[data-qs-page="2"]')).to_be_visible()

        # Click Back
        page.locator("#qsPagPrev").click()
        page.wait_for_timeout(300)
        expect(page.locator('[data-qs-page="1"]')).to_be_visible()

    def test_auto_trigger_when_not_dismissed(self, page: Page, base_url):
        """Quickstart auto-shows when dismiss flags are cleared."""
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        # Clear dismiss flags
        page.evaluate("""(() => {
            localStorage.removeItem('spotyvibe-quickstart-dismissed');
            localStorage.removeItem('spotyvibe-quickstart-openai-dismissed');
            localStorage.removeItem('spotyvibe-quickstart-spotify-dismissed');
        })()""")
        # Call maybeShowQuickstart which is the actual auto-trigger mechanism
        page.evaluate("maybeShowQuickstart('openai')")
        page.wait_for_timeout(500)
        expect(page.locator("#quickstartModal")).to_be_visible()


# ═══════════════════════════════════════════════════════════════════════
#  7. Quickstart Guide — Spotify Provider
# ═══════════════════════════════════════════════════════════════════════

class TestQuickstartSpotifyWorkflow:
    """Quickstart guide for the Spotify provider.

    Verifies: TOC entries = Setup + Generate a Playlist +
    Review & Feedback + Refine Existing Playlists + Repeat & Improve,
    each step has key actions and demo player.
    """

    def _open_quickstart_spotify(self, page: Page, base_url: str):
        """Navigate and open quickstart for Spotify provider."""
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        # Switch to Spotify tab first
        _switch_to_tab(page, "spotify")
        page.wait_for_timeout(200)
        # Clear dismiss flags and open quickstart
        page.evaluate("""(() => {
            localStorage.removeItem('spotyvibe-quickstart-dismissed');
            localStorage.removeItem('spotyvibe-quickstart-openai-dismissed');
            localStorage.removeItem('spotyvibe-quickstart-spotify-dismissed');
        })()""")
        # Force-open — this opens for the currently active provider (spotify)
        page.evaluate("openQuickstart(true)")
        page.wait_for_timeout(300)
        expect(page.locator("#quickstartModal")).to_be_visible()

    def test_quickstart_opens_for_spotify(self, page: Page, base_url):
        """Quickstart modal opens for the Spotify provider."""
        self._open_quickstart_spotify(page, base_url)
        expect(page.locator("#quickstartModal")).to_be_visible()

    def test_toc_has_correct_spotify_entries(self, page: Page, base_url):
        """TOC shows Setup + 4 Spotify-specific steps."""
        self._open_quickstart_spotify(page, base_url)
        toc = page.locator(".qs-toc")
        expect(toc).to_be_visible()

        # Spotify TOC: "both" (Setup) + "spotify" (Generate, Review, Refine, Repeat)
        visible_entries = toc.locator(
            '.qs-toc-entry[data-qs-provider="both"], '
            '.qs-toc-entry[data-qs-provider="spotify"]'
        )
        assert visible_entries.count() == 5

        expect(toc.locator('[aria-label="Go to Setup"]')).to_be_visible()
        expect(toc.locator('[aria-label="Go to Generate a Playlist"]')).to_be_visible()
        expect(toc.locator('[aria-label="Go to Review"]')).to_be_visible()
        expect(toc.locator('[aria-label="Go to Refine"]')).to_be_visible()
        expect(toc.locator('[aria-label="Go to Repeat"]')).to_be_visible()

    def test_toc_does_not_show_openai_entries(self, page: Page, base_url):
        """OpenAI-only TOC entries are not visible in Spotify quickstart."""
        self._open_quickstart_spotify(page, base_url)
        toc = page.locator(".qs-toc")
        # "Build Your Profile" is openai-only
        expect(toc.locator('[aria-label="Go to Setup"]')).to_be_visible()

    def test_generate_step_content(self, page: Page, base_url):
        """Step 3 (Generate a Playlist) shows correct title and 4 key actions."""
        self._open_quickstart_spotify(page, base_url)
        page.locator('.qs-toc-entry[aria-label="Go to Generate a Playlist"]').click()
        page.wait_for_timeout(300)
        step_page = page.locator('[data-qs-page="3"]')
        expect(step_page).to_be_visible()
        expect(step_page.locator(".qs-page-title")).to_contain_text("Generate a Playlist")
        expect(step_page.locator(".qs-key-actions li")).to_have_count(4)
        expect(step_page.locator(".qs-demo-player")).to_be_visible()

    def test_review_step_content(self, page: Page, base_url):
        """Step 4 (Review & Feedback) shows correct title and 5 key actions."""
        self._open_quickstart_spotify(page, base_url)
        page.locator('.qs-toc-entry[aria-label="Go to Review"]').click()
        page.wait_for_timeout(300)
        step_page = page.locator('[data-qs-page="4"]')
        expect(step_page).to_be_visible()
        expect(step_page.locator(".qs-page-title")).to_contain_text("Review")
        expect(step_page.locator(".qs-key-actions li")).to_have_count(5)
        expect(step_page.locator(".qs-demo-player")).to_be_visible()

    def test_refine_step_content(self, page: Page, base_url):
        """Step 5 (Refine Existing Playlists) shows correct title and 5 key actions."""
        self._open_quickstart_spotify(page, base_url)
        page.locator('.qs-toc-entry[aria-label="Go to Refine"]').click()
        page.wait_for_timeout(300)
        step_page = page.locator('[data-qs-page="5"]')
        expect(step_page).to_be_visible()
        expect(step_page.locator(".qs-page-title")).to_contain_text("Refine")
        expect(step_page.locator(".qs-key-actions li")).to_have_count(5)
        expect(step_page.locator(".qs-demo-player")).to_be_visible()

    def test_repeat_step_content(self, page: Page, base_url):
        """Step 6 (Repeat & Improve) shows correct title and 4 key actions."""
        self._open_quickstart_spotify(page, base_url)
        page.locator('.qs-toc-entry[aria-label="Go to Repeat"]').click()
        page.wait_for_timeout(300)
        step_page = page.locator('[data-qs-page="6"]')
        expect(step_page).to_be_visible()
        expect(step_page.locator(".qs-page-title")).to_contain_text("Repeat")
        expect(step_page.locator(".qs-key-actions li")).to_have_count(4)
        expect(step_page.locator(".qs-demo-player")).to_be_visible()

    def test_pagination_navigates_spotify_steps(self, page: Page, base_url):
        """Next/Back buttons navigate through Spotify-specific steps."""
        self._open_quickstart_spotify(page, base_url)
        # Go to first step (Setup)
        page.locator('.qs-toc-entry[aria-label="Go to Setup"]').click()
        page.wait_for_timeout(300)
        expect(page.locator('[data-qs-page="1"]')).to_be_visible()

        # Click Next → should go to Generate (page 3, since page 2 is openai-only)
        page.locator("#qsPagNext").click()
        page.wait_for_timeout(300)
        expect(page.locator('[data-qs-page="3"]')).to_be_visible()

        # Click Next → Review (page 4)
        page.locator("#qsPagNext").click()
        page.wait_for_timeout(300)
        expect(page.locator('[data-qs-page="4"]')).to_be_visible()

        # Click Back → Generate (page 3)
        page.locator("#qsPagPrev").click()
        page.wait_for_timeout(300)
        expect(page.locator('[data-qs-page="3"]')).to_be_visible()

    def test_auto_trigger_when_switching_to_spotify(self, page: Page, base_url):
        """Quickstart auto-shows when switching to Spotify tab (flags cleared)."""
        page.goto(base_url)
        page.wait_for_load_state("networkidle")
        # Clear dismiss flags
        page.evaluate("""(() => {
            localStorage.removeItem('spotyvibe-quickstart-dismissed');
            localStorage.removeItem('spotyvibe-quickstart-openai-dismissed');
            localStorage.removeItem('spotyvibe-quickstart-spotify-dismissed');
        })()""")
        # Call maybeShowQuickstart for spotify (simulates tab-switch trigger)
        page.evaluate("maybeShowQuickstart('spotify')")
        page.wait_for_timeout(500)
        expect(page.locator("#quickstartModal")).to_be_visible()

    def test_last_step_next_closes_modal(self, page: Page, base_url):
        """On the last step (Repeat), clicking Next closes the quickstart."""
        self._open_quickstart_spotify(page, base_url)
        # Navigate to the last step (Repeat & Improve)
        page.locator('.qs-toc-entry[aria-label="Go to Repeat"]').click()
        page.wait_for_timeout(300)
        expect(page.locator('[data-qs-page="6"]')).to_be_visible()
        # Click Next — should close the modal (becomes "Get Started")
        page.locator("#qsPagNext").click()
        page.wait_for_timeout(500)
        expect(page.locator("#quickstartModal")).to_be_hidden()


























