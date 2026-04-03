"""Pytest configuration for frontend tests — adds the spotyvibe directory to
sys.path and ensures Playwright browsers are available."""

import subprocess
import sys
from pathlib import Path

import pytest

# Allow imports like `from config import ...` and `from core.xxx import ...`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


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

