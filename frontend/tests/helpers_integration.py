"""Shared helpers, mock data, and server factory for workflow integration tests.

Each integration test file imports from here and creates its own
session-scoped Flask server via ``create_integration_server()``.
"""

import json
import socket
import threading
import time
from unittest.mock import patch

from playwright.sync_api import Page, expect


# ═══════════════════════════════════════════════════════════════════════
#  Navigation helpers
# ═══════════════════════════════════════════════════════════════════════

def switch_to_tab(page: Page, tab_name: str):
    """Click a tab and assert it became active.

    Waits for ``window.switchTab`` (the public surface of tabs.js) to be
    defined before clicking. Without this guard, fast tests race the ES
    module loader and the click is silently dropped, surfacing as a
    flaky aria-selected assertion timeout.
    """
    page.wait_for_load_state("load", timeout=30_000)
    page.wait_for_function("typeof window.switchTab === 'function'", timeout=30_000)
    tab = page.locator(f'[data-tab="{tab_name}"]')
    tab.wait_for(state="visible", timeout=10_000)
    tab.click()
    try:
        expect(tab).to_have_attribute("aria-selected", "true", timeout=5_000)
    except (AssertionError, Exception):
        page.wait_for_timeout(200)
        page.evaluate(f"window.switchTab && window.switchTab('{tab_name}')")
        expect(tab).to_have_attribute("aria-selected", "true", timeout=10_000)


def open_generate_section(page: Page):
    switch_to_tab(page, "spotify")
    body = page.locator("#generateBody")
    if not body.is_visible():
        page.locator("#generateToggleBtn").click()
        page.wait_for_timeout(300)
    expect(body).to_be_visible(timeout=10_000)


def open_review_section(page: Page):
    switch_to_tab(page, "spotify")
    body = page.locator("#reviewBody")
    if not body.is_visible():
        page.locator("#reviewToggleBtn").click()
        page.wait_for_timeout(300)
    expect(body).to_be_visible(timeout=10_000)


def open_analysis_section(page: Page):
    switch_to_tab(page, "openai")
    body = page.locator("#analysisBody")
    if not body.is_visible():
        page.locator("#analysisToggleBtn").click()
        page.wait_for_timeout(300)
    expect(body).to_be_visible(timeout=10_000)


def expand_dashboard(page: Page):
    body = page.locator("#dashboardBody")
    if not body.is_visible():
        page.locator("#dashboardToggleBtn").click()
        page.wait_for_timeout(500)
    expect(body).to_be_visible(timeout=10_000)
    expect(body).to_be_visible()


# ═══════════════════════════════════════════════════════════════════════
#  Mock data
# ═══════════════════════════════════════════════════════════════════════

# EMPTY_PROFILE / TRAINED_PROFILE live in _shared.py to keep this module and
# helpers.py from drifting apart. Re-exported here so existing
# `from helpers_integration import EMPTY_PROFILE` imports keep working.
from _shared import EMPTY_PROFILE, TRAINED_PROFILE  # noqa: F401

GENERATED_TRACKS_CREATE = [
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

GENERATED_TRACKS_APPEND = [
    {"artist": "Foo Fighters", "track": "Everlong", "reason": "Energetic anthem"},
    {"artist": "Royal Blood", "track": "Figure It Out", "reason": "Heavy riff"},
    {"artist": "Biffy Clyro", "track": "Many of Horror", "reason": "Emotional peak"},
    {"artist": "Nothing But Thieves", "track": "Amsterdam", "reason": "Atmospheric vocals"},
]

GENERATED_TRACKS_OVERRIDE_A = [
    {"artist": "Tool", "track": "Schism", "reason": "Complex progressive metal"},
    {"artist": "Deftones", "track": "Change", "reason": "Atmospheric alt metal"},
    {"artist": "System of a Down", "track": "Toxicity", "reason": "Intense and unique"},
]

GENERATED_TRACKS_OVERRIDE_B = [
    {"artist": "Porcupine Tree", "track": "Trains", "reason": "Melancholic prog rock"},
    {"artist": "Opeth", "track": "Harvest", "reason": "Beautiful acoustic prog"},
    {"artist": "Steven Wilson", "track": "Routine", "reason": "Emotional masterpiece"},
]

ANALYSIS_RESPONSE = {
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

PLAYLISTS = [
    {"id": "pl-create-1", "name": "Workflow Test Playlist"},
    {"id": "pl-append-1", "name": "Append Target"},
    {"id": "pl-replace-1", "name": "Replace Target"},
]

TASTE_DATA_CREATE = {
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

TASTE_DATA_EMPTY = {
    "tracks_considered": 0,
    "runs_considered": 0,
    "neutral": {"tracks_considered": 0, "top_genres": [], "energy_valence": [], "decades": []},
    "liked": {"tracks_considered": 0, "top_genres": [], "energy_valence": [], "decades": []},
    "disliked": {"tracks_considered": 0, "top_genres": [], "energy_valence": [], "decades": []},
}

HISTORY_CREATE = [
    {
        "timestamp": "2026-04-15T10:00:00",
        "playlist_url": "https://open.spotify.com/playlist/pl-create-1",
        "tracks": [
            {"artist": t["artist"], "track": t["track"],
             "energy": t.get("energy"), "valence": t.get("valence"),
             "genres": t.get("genres", []), "release_year": t.get("release_year"),
             "sentiment": "neutral"}
            for t in GENERATED_TRACKS_CREATE
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════
#  SSE builder
# ═══════════════════════════════════════════════════════════════════════

def build_sse_stream(tracks, playlist_url="https://open.spotify.com/playlist/test"):
    """Build an SSE body string for a successful generation run."""
    playlist_json = json.dumps(tracks)
    return (
        'data: {"type":"progress","message":"Batch 1: Asking the AI for suggestions…"}\n\n'
        f'data: {{"type":"batch_verified","count":{len(tracks)},"total":{len(tracks)}}}\n\n'
        f'data: {{"type":"result","playlist":{playlist_json},'
        f'"playlist_url":"{playlist_url}",'
        f'"playlist_id":"pl-gen-id",'
        f'"added":{len(tracks)},"not_found":[],"was_cancelled":false}}\n\n'
    )


# ═══════════════════════════════════════════════════════════════════════
#  Integration server factory
# ═══════════════════════════════════════════════════════════════════════

def create_integration_server():
    """Start a patched Flask app for integration tests. Returns (url, stop_fn)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    url = f"http://127.0.0.1:{port}"
    _profile_state = {"profile": dict(TRAINED_PROFILE), "trained": True}

    def fake_get_credentials():
        return {
            "OPENAI_API_KEY": {"masked": "****1234", "is_set": True},
            "SPOTIPY_CLIENT_ID": {"masked": "****c-id", "is_set": True},
            "SPOTIPY_CLIENT_SECRET": {"masked": "****c-se", "is_set": True},
        }

    def fake_get_settings():
        return {
            "model": "gpt-4.1-mini", "debug_mode": False,
            "debug_controls_available": True,
            "debug_log_path": "debug.log", "playlist_size": 10,
            "new_artist_percentage": 30,
        }

    patches = [
        patch("app.get_credentials", fake_get_credentials),
        patch("app.save_credentials", lambda data: None),
        patch("app.get_settings", fake_get_settings),
        patch("app.get_model", return_value="gpt-4.1-mini"),
        patch("app.get_openai_models", return_value=[
            {"id": "gpt-4.1-mini", "label": "gpt-4.1-mini", "supported": True},
        ]),
        patch("app.get_spotify_auth_status", return_value="authenticated"),
        patch("app.is_profile_trained", lambda: _profile_state["trained"]),
        patch("app.get_profile_status", lambda: (
            {"trained": True, "last_updated": "2025-01-01T00:00:00"}
            if _profile_state["trained"] else {"trained": False}
        )),
        patch("app.load_profile", lambda: dict(_profile_state["profile"])),
        patch("app.save_profile", lambda p: _profile_state.update({"profile": p})),
        patch("app.train_profile", lambda s: _profile_state.update({"trained": True}) or _profile_state["profile"]),
        patch("app.save_profile_sections", lambda s: _profile_state.update({"trained": True}) or _profile_state["profile"]),
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
        patch("app.list_profiles", return_value=[]),
        patch("app.create_profile", return_value={"id": "new-id", "name": "New"}),
        patch("app.delete_profile", return_value=None),
        patch("app.activate_profile", return_value=None),
        patch("app.get_active_profile_id", return_value=""),
        patch("app.aggregate_taste", return_value=TASTE_DATA_EMPTY),
        patch("app.load_runs", return_value=[]),
        patch("app.get_user_playlists", return_value=PLAYLISTS),
        patch("app.get_playlist_tracks", return_value=[]),
    ]

    for p in patches:
        p.start()

    from app import app as flask_app
    flask_app.config["TESTING"] = True

    # Use waitress (production WSGI server) instead of werkzeug's dev server.
    # werkzeug + threaded=True starves parallel test runners that fetch
    # main.js's ~30 ES-module imports concurrently.
    try:
        from waitress import serve as _waitress_serve
        server_target = lambda: _waitress_serve(
            flask_app, host="127.0.0.1", port=port, threads=8, _quiet=True,
        )
    except ImportError:
        server_target = lambda: flask_app.run(
            host="127.0.0.1", port=port, use_reloader=False, threaded=True,
        )

    server_thread = threading.Thread(target=server_target, daemon=True)
    server_thread.start()

    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)

    def stop():
        for p in patches:
            p.stop()

    return url, stop

