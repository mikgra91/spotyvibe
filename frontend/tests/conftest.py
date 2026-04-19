"""Pytest configuration for frontend tests — adds the spotyvibe directory to
sys.path and ensures Playwright browsers are available."""

import json
import logging
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Silence werkzeug's per-request INFO logging — test runs otherwise dump
# hundreds of "127.0.0.1 - - [ts] GET /static/..." lines that drown real signal.
logging.getLogger("werkzeug").setLevel(logging.WARNING)

# Enable HTTP/1.1 on the Flask dev server so the browser keeps TCP connections
# alive. Without this, every request closes its socket, and on Windows the
# resulting TIME_WAIT backlog exhausts ephemeral ports when several test
# groups run in parallel — surfacing as net::ERR_ADDRESS_IN_USE in Playwright.
from werkzeug.serving import WSGIRequestHandler
WSGIRequestHandler.protocol_version = "HTTP/1.1"

# Allow imports like `from config import ...` and `from core.xxx import ...`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
# Allow imports from helpers.py in this directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import free_port, EMPTY_PROFILE


@pytest.fixture(scope="session", autouse=True)
def _ensure_playwright_browsers():
    """Install Playwright's Chromium browser if it is not already present.

    Runs once per test session before any tests execute.  When the browser
    binary is already installed the check finishes in ~1 s; when it is
    missing, ``playwright install chromium`` is run automatically.

    This removes the manual install step — after ``pip install -r
    requirements.txt``, running ``pytest`` just works.
    """
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        browser.close()
        pw.stop()
    except Exception as exc:
        if "Executable doesn't exist" in str(exc):
            print("\n⏳ Playwright Chromium not found — installing…")
            subprocess.check_call(
                [sys.executable, "-m", "playwright", "install", "chromium"],
            )
            print("✅ Playwright Chromium installed.\n")
        else:
            # Some other error (e.g. import failure) — let it propagate
            # so the test session gives a clear error message.
            raise


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Force English locale so i18n doesn't auto-switch to German."""
    return {**browser_context_args, "locale": "en-US"}


@pytest.fixture(autouse=True)
def _reduce_timeouts(page):
    """Halve default Playwright timeouts and suppress the quickstart modal in tests.

    The quickstart auto-shows on first visit (no localStorage key).  Tests
    shouldn't need to dismiss it manually, so we inject the dismiss flag on
    every page-load event before any JS runs that would open the modal.
    """
    page.set_default_timeout(10_000)
    page.set_default_navigation_timeout(10_000)

    # Suppress the auto-show quickstart so modal doesn't block clicks.
    page.add_init_script(
        "localStorage.setItem('spotyvibe-quickstart-dismissed', 'true');"
    )


def dismiss_quickstart(page) -> None:
    """Close the quickstart modal if it is open, so tests can interact freely."""
    modal = page.locator("#quickstartModal")
    if modal.is_visible():
        page.evaluate("closeQuickstart()")


@pytest.fixture(scope="session")
def _base_url():
    """Start a patched Flask app in a background thread and return its URL.

    All external-facing APIs are mocked:
      - Credentials are fake (but pass the 'is_set' check)
      - Spotify auth status returns 'authenticated'
      - OpenAI model list returns a canned list
      - Profile is initially untrained (empty)
    """
    port = free_port()
    url = f"http://127.0.0.1:{port}"

    _profile_state = {"profile": dict(EMPTY_PROFILE), "trained": False}

    def fake_get_credentials():
        return {
            "OPENAI_API_KEY": {"masked": "****1234", "is_set": True},
            "SPOTIPY_CLIENT_ID": {"masked": "****c-id", "is_set": True},
            "SPOTIPY_CLIENT_SECRET": {"masked": "****c-se", "is_set": True},
        }

    def fake_save_credentials(data):
        pass

    def fake_get_settings():
        return {
            "model": "gpt-4.1-mini",
            "debug_mode": False,
            "debug_controls_available": True,
            "debug_log_path": "debug.log",
            "playlist_size": 10,
            "new_artist_percentage": 30,
            "provider_preset": "openai",
            "llm_api_key_required": True,
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
        patch("app.list_profiles", return_value=[
            {"id": "test-profile", "name": "Test Profile", "trained": False},
        ]),
        patch("app.get_active_profile_id", return_value="test-profile"),
        patch("app.create_profile", return_value={"id": "new-id", "name": "New"}),
        patch("app.delete_profile", return_value=None),
        patch("app.activate_profile", return_value=None),
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
    """Session-scoped fixture providing the server URL.

    Overrides pytest-playwright's built-in ``base_url`` so page.goto()
    resolves against our test server.
    """
    return _base_url

