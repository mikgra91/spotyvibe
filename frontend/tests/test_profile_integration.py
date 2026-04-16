"""Integration tests for profile switching, creation, and deletion.

Verifies that all profile-dependent UI components (taste dashboard, history,
track list, status box, playlist link) are properly reset when the active
profile changes — whether by switching, creating, or deleting a profile.

These tests use Playwright to drive a real browser against a Flask test server
with all external APIs mocked.  Profile CRUD endpoints are intercepted at the
Playwright level via ``page.route()`` so each test can control the exact
response data.
"""

import json
import re
import socket
import threading
import time
from unittest.mock import patch

import pytest
from playwright.sync_api import Page, expect


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
#  Fake data
# ---------------------------------------------------------------------------

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

# Two profiles for switch tests
PROFILE_A = {"id": "aaa-111", "name": "Rock", "trained": True, "last_updated": "2025-01-01T00:00:00"}
PROFILE_B = {"id": "bbb-222", "name": "Jazz", "trained": False, "last_updated": None}

_TASTE_DATA_WITH_CHARTS = {
    "tracks_considered": 25,
    "runs_considered": 3,
    "neutral": {
        "tracks_considered": 25,
        "top_genres": [
            {"genre": "rock", "count": 12},
            {"genre": "indie", "count": 8},
            {"genre": "pop", "count": 5},
        ],
        "energy_valence": [
            {"artist": "Muse", "title": "Hysteria", "energy": 0.9, "valence": 0.7},
            {"artist": "Radiohead", "title": "Airbag", "energy": 0.6, "valence": 0.3},
        ],
        "decades": [
            {"decade": "2000s", "count": 15},
            {"decade": "1990s", "count": 10},
        ],
    },
    "liked": {"tracks_considered": 0, "top_genres": [], "energy_valence": [], "decades": []},
    "disliked": {"tracks_considered": 0, "top_genres": [], "energy_valence": [], "decades": []},
}

_TASTE_DATA_EMPTY = {
    "tracks_considered": 0,
    "runs_considered": 0,
    "neutral": {"tracks_considered": 0, "top_genres": [], "energy_valence": [], "decades": []},
    "liked": {"tracks_considered": 0, "top_genres": [], "energy_valence": [], "decades": []},
    "disliked": {"tracks_considered": 0, "top_genres": [], "energy_valence": [], "decades": []},
}

_FAKE_HISTORY = [
    {
        "timestamp": "2026-04-10T14:30:00",
        "playlist_url": "https://open.spotify.com/playlist/hist1",
        "tracks": [
            {"artist": "History Artist 1", "track": "Old Song"},
            {"artist": "History Artist 2", "track": "Another Old Song"},
        ],
    },
]


# ---------------------------------------------------------------------------
#  Session-scoped Flask server
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def _base_url():
    """Start a patched Flask app with profile CRUD mocked."""
    port = _free_port()
    url = f"http://127.0.0.1:{port}"

    _profile_state = {"profile": dict(_EMPTY_PROFILE), "trained": False}

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
        # Profile CRUD — patched to no-ops so real filesystem is never touched
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


# ---------------------------------------------------------------------------
#  Route helpers — intercept APIs at Playwright level per test
# ---------------------------------------------------------------------------

def _route_profiles(page, profiles, active_id):
    """Intercept all /api/profiles* endpoints with a single handler.

    Playwright matches routes in LIFO order (last registered wins).
    We use a single catch-all handler to avoid glob-overlap issues between
    ``/api/profiles``, ``/api/profiles/<id>/activate``, and ``/api/profiles/<id>``.
    """
    state = {"profiles": list(profiles), "active_id": active_id}

    def handler(route):
        url = route.request.url
        method = route.request.method

        # POST /api/profiles/<id>/activate
        if "/activate" in url and method == "POST":
            parts = url.split("/api/profiles/")
            if len(parts) > 1:
                profile_id = parts[1].split("/activate")[0]
                state["active_id"] = profile_id
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"status": "ok"}))
            return

        # DELETE /api/profiles/<id>
        if method == "DELETE":
            parts = url.split("/api/profiles/")
            if len(parts) > 1:
                profile_id = parts[1].rstrip("/")
                state["profiles"] = [p for p in state["profiles"] if p["id"] != profile_id]
                if state["active_id"] == profile_id:
                    state["active_id"] = state["profiles"][0]["id"] if state["profiles"] else ""
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"status": "ok"}))
            return

        # POST /api/profiles  (create)
        if method == "POST":
            data = json.loads(route.request.post_data or "{}")
            new_id = "created-" + (data.get("name", "x")).lower().replace(" ", "-")
            new_profile = {"id": new_id, "name": data.get("name", "New"),
                           "trained": False, "last_updated": None}
            state["profiles"].append(new_profile)
            state["active_id"] = new_id
            route.fulfill(status=201, content_type="application/json",
                          body=json.dumps(new_profile))
            return

        # GET /api/profiles  (list)
        route.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"profiles": state["profiles"],
                             "active_id": state["active_id"]}),
        )

    page.route("**/api/profiles**", handler)
    return state


def _route_taste(page, taste_data):
    """Intercept GET /api/taste/aggregate."""
    state = {"data": taste_data}

    def handler(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(state["data"]),
        )

    page.route("**/api/taste/aggregate", handler)
    return state


def _route_runs(page, runs_data):
    """Intercept GET /api/runs."""
    state = {"runs": runs_data}

    def handler(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"runs": state["runs"]}),
        )

    page.route("**/api/runs", handler)
    return state


def _route_profile_status(page, trained=True):
    """Intercept GET /api/profile/status."""
    state = {"trained": trained}

    def handler(route):
        if state["trained"]:
            body = {"trained": True, "last_updated": "2025-01-01T00:00:00"}
        else:
            body = {"trained": False}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    page.route("**/api/profile/status", handler)
    return state


def _route_profile_data(page, profile_data):
    """Intercept GET /api/profile/data."""
    state = {"data": profile_data}

    def handler(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(state["data"]),
        )

    page.route("**/api/profile/data", handler)
    return state


def _open_profile_editor(page):
    """Ensure the Music Profile editor (#trainBody) is open."""
    body = page.locator("#trainBody")
    if not body.is_visible():
        page.locator("#trainToggleBtn").click()
    try:
        expect(body).to_be_visible(timeout=5_000)
    except AssertionError:
        page.locator("#trainToggleBtn").click()
        expect(body).to_be_visible(timeout=10_000)


def _expand_dashboard(page):
    """Expand the taste dashboard panel if collapsed."""
    body = page.locator("#dashboardBody")
    if not body.is_visible():
        page.locator("#dashboardToggleBtn").click()
    try:
        expect(body).to_be_visible(timeout=5_000)
    except AssertionError:
        # Retry — click may have been swallowed
        page.locator("#dashboardToggleBtn").click()
        expect(body).to_be_visible(timeout=10_000)


def _switch_to_tab(page, tab_name):
    """Click a tab and assert it becomes active (with switchTab() retry)."""
    page.wait_for_load_state("domcontentloaded")
    tab = page.locator(f'[data-tab="{tab_name}"]')
    tab.wait_for(state="visible", timeout=10_000)
    tab.click()
    try:
        expect(tab).to_have_attribute("aria-selected", "true", timeout=5_000)
    except (AssertionError, Exception):
        page.wait_for_timeout(100)
        page.evaluate(f"typeof switchTab === 'function' && switchTab('{tab_name}')")
        expect(tab).to_have_attribute("aria-selected", "true", timeout=10_000)


# ===================================================================
#  Test class: Profile Switch — Dashboard Reset
# ===================================================================

class TestProfileSwitchDashboard:
    """Switching profiles clears the taste dashboard and re-fetches data."""

    def test_switch_clears_dashboard_charts(self, page: Page, base_url):
        """After switching profiles, the dashboard charts are cleared and empty state shown."""
        # Set up: two profiles, A is active with chart data
        profile_state = _route_profiles(page, [PROFILE_A, PROFILE_B], PROFILE_A["id"])
        taste_state = _route_taste(page, _TASTE_DATA_WITH_CHARTS)
        _route_runs(page, _FAKE_HISTORY)
        _route_profile_status(page, trained=True)
        _route_profile_data(page, _TRAINED_PROFILE)

        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(500)

        # Expand dashboard — should show charts from profile A
        _expand_dashboard(page)

        # Verify charts are rendered (SVG elements inside dashboard cards)
        genres_card = page.locator("#dashboardNeutral .dashboard-card--genres svg")
        expect(genres_card).to_have_count(1)

        # Now switch taste data to empty for profile B
        taste_state["data"] = _TASTE_DATA_EMPTY

        # Open profile editor and switch to profile B via the custom dropdown
        _open_profile_editor(page)
        page.locator("#profileCustomDropdown").click()
        page.wait_for_timeout(100)
        page.locator(f'#profileDropdownList [data-value="{PROFILE_B["id"]}"]').click()
        page.wait_for_timeout(800)

        # Dashboard should be cleared — empty state visible
        empty = page.locator(".dashboard-empty")
        expect(empty).to_be_visible()

        # Chart SVGs should be gone
        genres_svg = page.locator("#dashboardNeutral .dashboard-card--genres svg")
        expect(genres_svg).to_have_count(0)

    def test_switch_refetches_dashboard_for_new_profile(self, page: Page, base_url):
        """Switching profiles fetches fresh taste data for the newly active profile."""
        profile_state = _route_profiles(page, [PROFILE_A, PROFILE_B], PROFILE_A["id"])
        # Start with empty taste data for profile A
        taste_state = _route_taste(page, _TASTE_DATA_EMPTY)
        _route_runs(page, [])
        _route_profile_status(page, trained=True)
        _route_profile_data(page, _TRAINED_PROFILE)

        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(500)

        _expand_dashboard(page)

        # Dashboard should show empty state for profile A
        expect(page.locator(".dashboard-empty")).to_be_visible()

        # Now profile B has chart data
        taste_state["data"] = _TASTE_DATA_WITH_CHARTS

        # Switch to profile B
        _open_profile_editor(page)
        page.locator("#profileCustomDropdown").click()
        page.wait_for_timeout(100)
        page.locator(f'#profileDropdownList [data-value="{PROFILE_B["id"]}"]').click()
        page.wait_for_timeout(800)

        # Dashboard should now show charts from profile B
        genres_card = page.locator("#dashboardNeutral .dashboard-card--genres svg")
        expect(genres_card).to_have_count(1)

    def test_dashboard_empty_state_after_switch_when_collapsed(self, page: Page, base_url):
        """If dashboard is collapsed during switch, expanding it shows fresh data."""
        profile_state = _route_profiles(page, [PROFILE_A, PROFILE_B], PROFILE_A["id"])
        taste_state = _route_taste(page, _TASTE_DATA_WITH_CHARTS)
        _route_runs(page, _FAKE_HISTORY)
        _route_profile_status(page, trained=True)
        _route_profile_data(page, _TRAINED_PROFILE)

        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(500)

        # Do NOT expand dashboard — leave it collapsed

        # Switch taste to empty for profile B
        taste_state["data"] = _TASTE_DATA_EMPTY

        # Switch to profile B
        _open_profile_editor(page)
        page.locator("#profileCustomDropdown").click()
        page.wait_for_timeout(100)
        page.locator(f'#profileDropdownList [data-value="{PROFILE_B["id"]}"]').click()
        page.wait_for_timeout(500)

        # Now expand dashboard — should fetch fresh empty data
        _expand_dashboard(page)

        expect(page.locator(".dashboard-empty")).to_be_visible()
        expect(page.locator("#dashboardNeutral .dashboard-card--genres svg")).to_have_count(0)


# ===================================================================
#  Test class: Profile Creation — State Reset
# ===================================================================

class TestProfileCreateStateReset:
    """Creating a new profile resets all profile-dependent UI state."""

    def test_create_profile_clears_dashboard(self, page: Page, base_url):
        """After creating a new profile, dashboard shows empty state, not stale charts."""
        profile_state = _route_profiles(page, [PROFILE_A], PROFILE_A["id"])
        taste_state = _route_taste(page, _TASTE_DATA_WITH_CHARTS)
        _route_runs(page, _FAKE_HISTORY)
        _route_profile_status(page, trained=True)
        _route_profile_data(page, _TRAINED_PROFILE)

        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(500)

        # Expand dashboard — charts from profile A
        _expand_dashboard(page)
        expect(page.locator("#dashboardNeutral .dashboard-card--genres svg")).to_have_count(1)

        # Switch taste to empty for the new profile
        taste_state["data"] = _TASTE_DATA_EMPTY

        # Create a new profile
        _open_profile_editor(page)
        page.locator("#profileCreateToggle").click()
        page.wait_for_timeout(100)
        page.locator("#profileCreateInput").fill("Workout")
        page.locator("#profileCreateInput").press("Enter")
        page.wait_for_timeout(800)

        # Dashboard should be reset — empty state, no stale charts
        expect(page.locator(".dashboard-empty")).to_be_visible()
        expect(page.locator("#dashboardNeutral .dashboard-card--genres svg")).to_have_count(0)

    def test_create_profile_clears_history(self, page: Page, base_url):
        """After creating a new profile, history shows empty state."""
        profile_state = _route_profiles(page, [PROFILE_A], PROFILE_A["id"])
        _route_taste(page, _TASTE_DATA_EMPTY)
        runs_state = _route_runs(page, _FAKE_HISTORY)
        _route_profile_status(page, trained=True)
        _route_profile_data(page, _TRAINED_PROFILE)

        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(500)

        # Switch to history tab and verify history items exist
        _switch_to_tab(page, "history")
        page.evaluate("loadHistory()")
        page.wait_for_timeout(200)
        expect(page.locator("#historyList .history-run-item")).to_have_count(1)

        # Switch runs to empty for the new profile
        runs_state["runs"] = []

        # Switch back to OpenAI tab and create a new profile
        _switch_to_tab(page, "openai")
        _open_profile_editor(page)
        page.locator("#profileCreateToggle").click()
        page.wait_for_timeout(100)
        page.locator("#profileCreateInput").fill("Chill")
        page.locator("#profileCreateInput").press("Enter")
        page.wait_for_timeout(800)

        # Switch to history tab — should show empty
        _switch_to_tab(page, "history")
        page.evaluate("loadHistory()")
        page.wait_for_timeout(200)
        expect(page.locator("#historyList")).to_contain_text("No runs yet.")

    def test_create_profile_clears_status_box(self, page: Page, base_url):
        """After creating a new profile, the status box is cleared/hidden."""
        profile_state = _route_profiles(page, [PROFILE_A], PROFILE_A["id"])
        _route_taste(page, _TASTE_DATA_EMPTY)
        _route_runs(page, [])
        status_state = _route_profile_status(page, trained=True)
        _route_profile_data(page, _TRAINED_PROFILE)

        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(500)

        # Inject some text into the status box to simulate a previous run.
        # The statusBox is inside the Spotify panel (hidden by default),
        # so we verify via DOM class rather than Playwright visibility.
        page.evaluate("""
            const sb = document.getElementById('statusBox');
            if (sb) { sb.textContent = 'Generation complete!'; sb.classList.remove('hidden'); }
        """)
        has_content = page.locator("#statusBox").evaluate(
            "el => !el.classList.contains('hidden') && el.textContent.trim() !== ''"
        )
        assert has_content, "Pre-condition: status box should have content"

        # Now switch profile status to untrained for the new profile
        status_state["trained"] = False

        # Create a new profile
        _open_profile_editor(page)
        page.locator("#profileCreateToggle").click()
        page.wait_for_timeout(100)
        page.locator("#profileCreateInput").fill("Discovery")
        page.locator("#profileCreateInput").press("Enter")
        page.wait_for_timeout(800)

        # Status box should be cleared
        status_box = page.locator("#statusBox")
        is_hidden = status_box.evaluate("el => el.classList.contains('hidden') || el.textContent.trim() === ''")
        assert is_hidden, "Status box should be hidden or empty after creating a new profile"


# ===================================================================
#  Test class: Profile Switch — History and Track List Reset
# ===================================================================

class TestProfileSwitchHistoryAndTracks:
    """Switching profiles reloads history and clears the track list."""

    def test_switch_reloads_history(self, page: Page, base_url):
        """After switching profiles, the history panel shows the new profile's runs."""
        profile_state = _route_profiles(page, [PROFILE_A, PROFILE_B], PROFILE_A["id"])
        _route_taste(page, _TASTE_DATA_EMPTY)
        runs_state = _route_runs(page, _FAKE_HISTORY)
        _route_profile_status(page, trained=True)
        _route_profile_data(page, _TRAINED_PROFILE)

        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(500)

        # Open history tab and verify runs
        _switch_to_tab(page, "history")
        page.evaluate("loadHistory()")
        page.wait_for_timeout(200)
        expect(page.locator("#historyList .history-run-item")).to_have_count(1)

        # Switch runs to empty for profile B
        runs_state["runs"] = []

        # Switch to OpenAI tab and switch profile
        _switch_to_tab(page, "openai")
        _open_profile_editor(page)
        page.locator("#profileCustomDropdown").click()
        page.wait_for_timeout(100)
        page.locator(f'#profileDropdownList [data-value="{PROFILE_B["id"]}"]').click()
        page.wait_for_timeout(800)

        # History should show empty (profile B has no runs)
        _switch_to_tab(page, "history")
        page.evaluate("loadHistory()")
        page.wait_for_timeout(200)
        expect(page.locator("#historyList")).to_contain_text("No runs yet.")

    def test_switch_clears_track_list(self, page: Page, base_url):
        """After switching profiles, generated track cards are removed."""
        profile_state = _route_profiles(page, [PROFILE_A, PROFILE_B], PROFILE_A["id"])
        _route_taste(page, _TASTE_DATA_EMPTY)
        _route_runs(page, [])
        _route_profile_status(page, trained=True)
        _route_profile_data(page, _TRAINED_PROFILE)

        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(500)

        # Inject some fake track cards into the track list via JS
        page.evaluate("""
            const container = document.getElementById('trackList');
            if (container) {
                for (let i = 0; i < 3; i++) {
                    const card = document.createElement('div');
                    card.className = 'track-item';
                    card.textContent = 'Fake Track ' + i;
                    container.appendChild(card);
                }
            }
        """)
        expect(page.locator("#trackList .track-item")).to_have_count(3)

        # Switch to profile B
        _open_profile_editor(page)
        page.locator("#profileCustomDropdown").click()
        page.wait_for_timeout(100)
        page.locator(f'#profileDropdownList [data-value="{PROFILE_B["id"]}"]').click()
        page.wait_for_timeout(800)

        # Track list should be empty
        expect(page.locator("#trackList .track-item")).to_have_count(0)

    def test_switch_hides_playlist_link(self, page: Page, base_url):
        """After switching profiles, the playlist link box has 'hidden' class."""
        profile_state = _route_profiles(page, [PROFILE_A, PROFILE_B], PROFILE_A["id"])
        _route_taste(page, _TASTE_DATA_EMPTY)
        _route_runs(page, [])
        _route_profile_status(page, trained=True)
        _route_profile_data(page, _TRAINED_PROFILE)

        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(500)

        # Inject a playlist link and remove 'hidden' class.
        # The element is inside the Spotify panel (hidden tab by default),
        # so we check via DOM class rather than Playwright visibility.
        page.evaluate("""
            const box = document.getElementById('playlistLinkBox');
            if (box) {
                box.classList.remove('hidden');
                box.innerHTML = '<a href="https://open.spotify.com/playlist/test">Open playlist</a>';
            }
        """)
        has_link = page.locator("#playlistLinkBox").evaluate(
            "el => !el.classList.contains('hidden')"
        )
        assert has_link, "Pre-condition: playlistLinkBox should not have 'hidden' class"

        # Switch to profile B
        _open_profile_editor(page)
        page.locator("#profileCustomDropdown").click()
        page.wait_for_timeout(100)
        page.locator(f'#profileDropdownList [data-value="{PROFILE_B["id"]}"]').click()
        page.wait_for_timeout(800)

        # Playlist link should have 'hidden' class
        is_hidden = page.locator("#playlistLinkBox").evaluate(
            "el => el.classList.contains('hidden')"
        )
        assert is_hidden, "Playlist link box should have 'hidden' class after profile switch"

    def test_switch_dismisses_draft_banner(self, page: Page, base_url):
        """After switching profiles, the playlist seed draft banner has 'hidden' class."""
        profile_state = _route_profiles(page, [PROFILE_A, PROFILE_B], PROFILE_A["id"])
        _route_taste(page, _TASTE_DATA_EMPTY)
        _route_runs(page, [])
        _route_profile_status(page, trained=True)
        _route_profile_data(page, _TRAINED_PROFILE)

        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(500)

        # Show the draft banner (it lives inside #trainBody which may be collapsed,
        # so we check via DOM class rather than Playwright visibility).
        page.evaluate("""
            const banner = document.getElementById('profileDraftBanner');
            if (banner) banner.classList.remove('hidden');
        """)
        is_shown = page.locator("#profileDraftBanner").evaluate(
            "el => !el.classList.contains('hidden')"
        )
        assert is_shown, "Pre-condition: draft banner should not have 'hidden' class"

        # Switch to profile B
        _open_profile_editor(page)
        page.locator("#profileCustomDropdown").click()
        page.wait_for_timeout(100)
        page.locator(f'#profileDropdownList [data-value="{PROFILE_B["id"]}"]').click()
        page.wait_for_timeout(800)

        # Draft banner should have 'hidden' class
        is_hidden = page.locator("#profileDraftBanner").evaluate(
            "el => el.classList.contains('hidden')"
        )
        assert is_hidden, "Draft banner should have 'hidden' class after profile switch"


# ===================================================================
#  Test class: Taste Dashboard Isolation
# ===================================================================

class TestTasteDashboardIsolation:
    """Taste dashboard respects profile boundaries."""

    def test_empty_profile_shows_empty_dashboard(self, page: Page, base_url):
        """A profile with no runs shows the empty dashboard state."""
        _route_profiles(page, [PROFILE_B], PROFILE_B["id"])
        _route_taste(page, _TASTE_DATA_EMPTY)
        _route_runs(page, [])
        _route_profile_status(page, trained=False)
        _route_profile_data(page, _EMPTY_PROFILE)

        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(500)

        _expand_dashboard(page)

        expect(page.locator(".dashboard-empty")).to_be_visible()
        expect(page.locator("#dashboardNeutral .dashboard-card--genres svg")).to_have_count(0)

    def test_profile_with_data_shows_charts(self, page: Page, base_url):
        """A profile with enough runs shows charts in the dashboard."""
        _route_profiles(page, [PROFILE_A], PROFILE_A["id"])
        _route_taste(page, _TASTE_DATA_WITH_CHARTS)
        _route_runs(page, _FAKE_HISTORY)
        _route_profile_status(page, trained=True)
        _route_profile_data(page, _TRAINED_PROFILE)

        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(500)

        _expand_dashboard(page)

        # Should have all three charts
        expect(page.locator("#dashboardNeutral .dashboard-card--genres svg")).to_have_count(1)
        expect(page.locator("#dashboardNeutral .dashboard-card--scatter svg")).to_have_count(1)
        expect(page.locator("#dashboardNeutral .dashboard-card--decades svg")).to_have_count(1)

        # Empty state should be hidden
        expect(page.locator(".dashboard-empty")).to_be_hidden()

    def test_dashboard_info_shows_track_count(self, page: Page, base_url):
        """When charts are rendered, the info line shows track/run count."""
        _route_profiles(page, [PROFILE_A], PROFILE_A["id"])
        _route_taste(page, _TASTE_DATA_WITH_CHARTS)
        _route_runs(page, _FAKE_HISTORY)
        _route_profile_status(page, trained=True)
        _route_profile_data(page, _TRAINED_PROFILE)

        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(500)

        _expand_dashboard(page)

        info = page.locator("#dashboardInfo")
        expect(info).to_be_visible()
        # Should mention track count (25) and run count (3)
        info_text = info.inner_text()
        assert "25" in info_text
        assert "3" in info_text




