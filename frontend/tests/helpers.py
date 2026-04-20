"""Shared helpers and mock data for frontend Playwright tests.

Imported by all test_*.py files in this directory.
"""

import json
import re

from playwright.sync_api import Page, expect


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def free_port():
    """Return a free TCP port on localhost."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def switch_to_tab(page: Page, tab_name: str):
    """Click a tab and assert it actually became active.

    main.js is a large ES module (~30 imports). Under parallel-test load on
    the Flask dev server, full evaluation can take longer than the default
    timeout. We wait for the ``load`` state (not just ``domcontentloaded``)
    and then for ``window.switchTab`` to be defined — that's the signal
    that tabs.js has wired its click handlers. Without this guard, fast
    tests race the loader and the click is silently dropped.
    """
    page.wait_for_load_state("load", timeout=30_000)
    page.wait_for_function("typeof window.switchTab === 'function'", timeout=30_000)
    tab = page.locator(f'[data-tab="{tab_name}"]')
    tab.wait_for(state="visible", timeout=10_000)
    tab.click()
    try:
        expect(tab).to_have_attribute("aria-selected", "true", timeout=5_000)
    except (AssertionError, Exception):
        # Fall back to calling switchTab() directly via JS.
        page.wait_for_timeout(150)
        page.evaluate(f"window.switchTab && window.switchTab('{tab_name}')")
        expect(tab).to_have_attribute("aria-selected", "true", timeout=10_000)


def open_profile_editor(page: Page):
    """Ensure the Music Profile editor (#trainBody) is open."""
    body = page.locator("#trainBody")
    if not body.is_visible():
        btn = page.locator("#trainToggleBtn")
        btn.wait_for(state="visible", timeout=5_000)
        btn.click()
    try:
        expect(body).to_be_visible(timeout=5_000)
    except AssertionError:
        # Retry — click may not have registered (JS not ready yet)
        page.locator("#trainToggleBtn").click()
        expect(body).to_be_visible(timeout=10_000)


def close_profile_editor(page: Page):
    """Ensure the Music Profile editor (#trainBody) is closed."""
    body = page.locator("#trainBody")
    if body.is_visible():
        page.locator("#trainToggleBtn").click()
    expect(body).to_be_hidden(timeout=10_000)


def open_generate_section(page: Page):
    """Switch to the Spotify tab, expand the Generate section, and assert both."""
    switch_to_tab(page, "spotify")
    body = page.locator("#generateBody")
    if not body.is_visible():
        page.locator("#generateToggleBtn").click()
    expect(body).to_be_visible(timeout=10_000)


def open_burger_menu(page: Page):
    """Open the burger menu and assert it opened.

    Waits for the JS module that wires the burger button (settings.js exposes
    ``window.toggleSettings``) before clicking — prevents a race where the
    click happens before the handler is attached.
    """
    # Ensure tabs/settings JS is initialized — switchTab is the canary that the
    # full main.js wiring is done.
    page.wait_for_load_state("load", timeout=30_000)
    page.wait_for_function("typeof window.switchTab === 'function'", timeout=30_000)
    page.locator('button[aria-label="Menu"]').click()
    try:
        expect(page.locator("#settingsDropdown")).to_have_class(re.compile(r"open"), timeout=5_000)
    except (AssertionError, Exception):
        # Fallback: click again — handler may have attached just after first click.
        page.wait_for_timeout(200)
        page.locator('button[aria-label="Menu"]').click()
        expect(page.locator("#settingsDropdown")).to_have_class(re.compile(r"open"), timeout=10_000)


def open_analysis_section(page: Page):
    """Switch to the openai tab, expand Band/Song Analysis, and assert both."""
    switch_to_tab(page, "openai")
    body = page.locator("#analysisBody")
    if not body.is_visible():
        page.locator("#analysisToggleBtn").click()
    expect(body).to_be_visible(timeout=10_000)


def open_review_section(page: Page):
    """Switch to the spotify tab, expand Refine Playlist, and assert both."""
    switch_to_tab(page, "spotify")
    body = page.locator("#reviewBody")
    if not body.is_visible():
        page.locator("#reviewToggleBtn").click()
    expect(body).to_be_visible(timeout=10_000)


def open_audio_filters(page: Page):
    """Inside the generate section (already open), switch to Advanced mode
    and expand Audio Filters sub-panel."""
    page.locator(".gen-mode-btn[data-mode='advanced']").click()
    body = page.locator("#audioFiltersBody")
    if not body.is_visible():
        page.locator(".audio-filter-toggle").click()
    expect(body).to_be_visible()


def open_quickstart(page: Page):
    """Open the quickstart modal via JS (force=true) and assert it is visible."""
    page.evaluate("openQuickstart(true)")
    expect(page.locator("#quickstartModal")).to_be_visible()


def navigate_onboarding_to_page(page: Page, base_url: str, target_page: int):
    """Navigate to /onboarding (with incomplete status) and advance to target_page (0-6).

    Page 0 = Welcome, 1 = OpenAI key, 2 = Spotify cred, 3 = Connect Spotify,
    4 = Model, 5 = Seed taste, 6 = Ready.
    """
    page.route("**/api/onboarding/status", lambda route: route.fulfill(
        status=200,
        headers={"Content-Type": "application/json"},
        body=json.dumps({"completed": False}),
    ))
    page.goto(base_url + "/onboarding?replay=1", wait_until="domcontentloaded")
    page.locator(".ob-page.active").wait_for(timeout=5000)
    page.wait_for_timeout(400)
    for i in range(target_page):
        cta = page.locator(".ob-page.active .ob-cta-start, .ob-page.active .ob-cta-skip-inline").first
        cta.scroll_into_view_if_needed()
        # Use JS click to avoid Playwright's "outside of viewport" auto-retry
        # when the wizard card ends up taller than the viewport on small
        # screens. The button is fully functional via its inline onclick.
        cta.evaluate("el => el.click()")
        page.locator(".ob-page.active").wait_for(timeout=3000)
        page.wait_for_timeout(200)


# ---------------------------------------------------------------------------
#  Mock data constants
# ---------------------------------------------------------------------------

FAKE_CREDENTIALS = {
    "OPENAI_API_KEY": "sk-test-fake-key-1234",
    "OPENAI_MODEL": "gpt-4.1-mini",
    "SPOTIPY_CLIENT_ID": "fake-client-id",
    "SPOTIPY_CLIENT_SECRET": "fake-client-secret",
    "DEBUG_MODE": "",
    "PLAYLIST_SIZE": "10",
    "NEW_ARTIST_PERCENTAGE": "30",
}

EMPTY_PROFILE = {
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

TRAINED_PROFILE = {
    **EMPTY_PROFILE,
    "preferences": {
        "core_description": "Upbeat theatrical rock with strong melodies",
        "must_have": ["high energy", "strong melodies"],
        "soft_preferences": ["slight prog influence"],
        "avoid": ["electronic production"],
    },
    "last_updated": "2025-01-01T00:00:00",
}

FAKE_ANALYSIS_RESPONSE = {
    "artist": "Muse",
    "track": "Uprising",
    "genre": "Alternative Rock",
    "style_tags": ["theatrical", "electronic rock", "anthemic"],
    "characteristics": {
        "energy": 0.85,
        "valence": 0.65,
        "tempo": 128,
        "danceability": 0.60,
        "acousticness": 0.05,
    },
    "profile_suggestions": {
        "core_description": "High-energy theatrical rock with electronic elements",
        "must_have": ["driving rhythms", "anthemic choruses"],
        "soft_preferences": ["electronic textures"],
        "avoid": ["acoustic stripped-down"],
    },
}

FAKE_PLAYLISTS = [
    {"id": "pl1", "name": "My Rock Mix"},
    {"id": "pl2", "name": "Chill Vibes"},
]

FAKE_REVIEW_TRACKS = [
    {
        "artist": "Review Artist",
        "track": "Review Song",
        "track_id": "rt1",
        "cover_url": "https://example.com/cover1.jpg",
        "reason": "Great energy",
    },
    {
        "artist": "Another Review",
        "track": "Slow Jam",
        "track_id": "rt2",
        "cover_url": "https://example.com/cover2.jpg",
        "reason": "Mellow vibes",
    },
]

FAKE_HISTORY = [
    {
        "timestamp": "2026-04-10T14:30:00",
        "playlist_url": "https://open.spotify.com/playlist/hist1",
        "tracks": [
            {"artist": "History Artist 1", "track": "Old Song"},
            {"artist": "History Artist 2", "track": "Another Old Song"},
        ],
    },
    {
        "timestamp": "2026-04-09T10:00:00",
        "playlist_url": "https://open.spotify.com/playlist/hist2",
        "tracks": [
            {"artist": "Yesterday Band", "track": "Past Hit"},
        ],
    },
]

