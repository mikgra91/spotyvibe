"""WS3 — untrusted Spotify data must be escaped at DOM sinks.

Regression for the playlist-seed cover_url sink: a crafted cover URL must
not break out of the <img src="..."> attribute and execute script. The
fix routes cover_url through the attribute escaper (ui.js ``attr``).
"""
import json

from playwright.sync_api import Page


# Breaks out of src="..." and adds an onerror handler under the OLD code.
XSS_COVER = 'x" onerror="window.__xss=1" data-x="'

PAYLOAD_PLAYLISTS = [{
    "id": "p1", "name": "Normal Name", "owner": "me",
    "track_count": 5, "cover_url": XSS_COVER,
}]


def test_seed_cover_url_is_escaped(page: Page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("domcontentloaded")
    page.route("**/api/profile/status", lambda r: r.fulfill(
        status=200, headers={"Content-Type": "application/json"},
        body=json.dumps({"trained": False})))
    page.route("**/api/spotify/playlists_for_seed", lambda r: r.fulfill(
        status=200, headers={"Content-Type": "application/json"},
        body=json.dumps({"playlists": PAYLOAD_PLAYLISTS})))

    page.evaluate("window.openPlaylistSeedPicker('profile')")
    page.locator("#playlistSeedList .playlist-seed-item").first.wait_for(timeout=5000)
    page.wait_for_timeout(200)  # allow any img onerror to fire if injected

    # No script executed …
    assert not page.evaluate("window.__xss")
    # … the payload survives only as the literal src value (no parsed attrs) …
    cover = page.locator(".playlist-seed-cover").first
    assert cover.get_attribute("src") == XSS_COVER
    # … and no rogue onerror attribute was created.
    assert cover.get_attribute("onerror") is None
