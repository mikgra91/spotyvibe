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


# ── Track-card inline cover handler (feedback.js buildTrackCardHtml) ──────────
# Old code embedded track.artist/track/track_id directly inside the inline
# onclick="openPreviewOverlay('…','<artist> — <track>','…')". attr() escapes
# quotes to HTML entities, but the HTML parser decodes them before the JS
# string is evaluated, so this payload broke out of the JS literal and ran.
JS_BREAKOUT = "x');window.__xss=1;//"


def _render_one_track(page, base_url, artist, track):
    page.goto(base_url)
    page.wait_for_load_state("domcontentloaded")
    page.evaluate(
        """async ({artist, track}) => {
            const State = await import('/static/js/modules/state.js');
            State.setSuggestions([{
                artist, track, track_id: '0abc123', cover_url: 'https://e.test/c.jpg',
                rationale: [],
            }]);
            window.renderTracks();
        }""",
        {"artist": artist, "track": track},
    )
    # The discover section may be behind an inactive tab (hidden), so wait for
    # the node to be attached rather than visible.
    page.locator(".track-cover-wrap").first.wait_for(state="attached", timeout=5000)


def test_track_cover_handler_carries_no_untrusted_data(page: Page, base_url):
    """The inline cover handler must pass only the numeric index + source —
    never the artist/track strings — so a crafted name cannot break out."""
    _render_one_track(page, base_url, JS_BREAKOUT, "Song")
    onclick = page.locator(".track-cover-wrap").first.get_attribute("onclick")
    assert onclick == "openPreviewByIndex(0,'discover')"
    # The payload must not appear anywhere in the handler.
    assert "__xss" not in onclick
    assert "window" not in onclick


def test_malicious_track_name_does_not_execute_on_click(page: Page, base_url):
    """Clicking the cover of a track with a JS-breakout artist name opens the
    preview overlay (behavior preserved) without executing injected script."""
    _render_one_track(page, base_url, JS_BREAKOUT, "Song")
    # dispatch_event fires the real inline onclick regardless of visibility.
    page.locator(".track-cover-wrap").first.dispatch_event("click")
    page.wait_for_timeout(150)
    assert not page.evaluate("window.__xss")
    # Overlay opened from the index-resolved track → feature still works.
    assert "visible" in (page.locator("#spotifyPreviewOverlay").get_attribute("class") or "")


def test_malicious_artist_rendered_as_escaped_text(page: Page, base_url):
    """An HTML-injection artist name renders as inert text, not live markup."""
    payload = "<img src=x onerror=window.__xss=1>Bad Artist"
    _render_one_track(page, base_url, payload, "Song")
    page.wait_for_timeout(150)
    assert not page.evaluate("window.__xss")
    # No injected <img> node exists inside the track name.
    assert page.locator(".track-name img").count() == 0
    # The literal text is preserved (escaped), proving text-context escaping.
    assert "Bad Artist" in (page.locator(".track-name").first.text_content() or "")
