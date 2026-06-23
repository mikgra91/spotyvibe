"""Edge cases, SSE reconnection, and robustness tests."""

import json
import re

import pytest
from playwright.sync_api import Page, expect

from helpers import (
    switch_to_tab, open_generate_section, open_analysis_section,
    open_burger_menu, open_profile_editor,
    FAKE_ANALYSIS_RESPONSE,
)


class TestEdgeCases:
    """Robustness — rapid actions, special input, API errors, concurrent modals."""

    def test_rapid_tab_switching(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        for _ in range(3):
            page.locator('[data-tab="openai"]').click()
            page.locator('[data-tab="spotify"]').click()
            page.locator('[data-tab="history"]').click()
        expect(page.locator('[data-tab="history"]')).to_have_attribute(
            "aria-selected", "true"
        )
        expect(page.locator("#historyPanel")).to_be_visible()

    def test_rapid_theme_switching(self, page: Page, base_url):
        page.goto(base_url)
        for _ in range(5):
            page.locator('[data-theme="pulse"]').click()
            page.locator('[data-theme="equalizer"]').click()
        expect(page.locator("body")).to_have_class(re.compile(r"theme-equalizer"))
        expect(page.locator("body")).not_to_have_class(re.compile(r"theme-pulse"))

    def test_very_long_profile_text_accepted(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_profile_editor(page)
        long_text = "A" * 1000
        page.locator("#trainCoreDesc").fill(long_text)
        page.locator("#trainSaveBtn").click()
        toast = page.locator("#toast")
        expect(toast).to_be_visible(timeout=2000)

    def test_special_characters_in_analysis_input(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        open_analysis_section(page)
        sent_bodies = []
        page.route("**/api/analyze", lambda route: (
            sent_bodies.append(route.request.post_data_json),
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps(FAKE_ANALYSIS_RESPONSE),
            ),
        )[1])
        xss_input = "<script>alert(1)</script>"
        page.locator("#analysisArtist").fill(xss_input)
        page.locator("#analysisSendBtn").click()
        page.wait_for_timeout(150)
        if sent_bodies:
            assert sent_bodies[0]["artist"] == xss_input
        value = page.locator("#analysisArtist").input_value()
        assert "<script>" in value or len(value) == 0

    def test_empty_generation_result_handled(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.route("**/api/run", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
            body='data: {"type":"result","playlist":[],"playlist_url":"","added":0,"not_found":[],"was_cancelled":false}\n\n',
        ))
        page.route("**/api/profile/status", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"trained": True, "last_updated": "2025-01-01T00:00:00"}),
        ))
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        open_generate_section(page)
        page.locator("#runBtn").click()
        expect(page.locator("#runBtn")).to_be_enabled(timeout=3000)
        assert page.locator(".track-item").count() == 0

    def test_api_error_during_generation_re_enables_button(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.route("**/api/run", lambda route: route.fulfill(
            status=500,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"error": "Internal server error"}),
        ))
        page.route("**/api/profile/status", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"trained": True, "last_updated": "2025-01-01T00:00:00"}),
        ))
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        open_generate_section(page)
        page.locator("#runBtn").click()
        expect(page.locator("#runBtn")).to_be_enabled(timeout=3000)

    def test_concurrent_modals_only_one_open(self, page: Page, base_url):
        page.goto(base_url)
        open_burger_menu(page)
        page.locator("#settingsDropdown >> text=Credentials").click()
        expect(page.locator("#credentialsModal")).to_have_class(re.compile(r"open"))
        page.evaluate("closeModal('credentialsModal')")
        page.wait_for_timeout(100)
        page.evaluate("openSettings()")
        page.wait_for_timeout(100)
        expect(page.locator("#settingsModal")).to_have_class(re.compile(r"open"))

    def test_double_click_generate_single_request(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        run_calls = []

        def handle_run(route):
            # Intentionally NEVER fulfill — the double-click guard is an
            # "in-flight protection" check (the runBtn stays disabled
            # while the SSE request is open). Letting the route hang
            # keeps it open for the duration of the test, so the second
            # click happens *during* the first request and is the only
            # signal that exercises the guard.
            run_calls.append(1)

        page.route("**/api/profile/status", lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"trained": True, "last_updated": "2025-01-01T00:00:00"}),
        ))
        page.route("**/api/run", handle_run)
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        open_generate_section(page)
        page.locator("#runBtn").click()
        try:
            page.locator("#runBtn").click(timeout=500)
        except Exception:
            pass
        # Wait long enough that a second request would have arrived if
        # the guard were broken. Bumped from 250 ms → 750 ms for
        # parallel-CI tolerance.
        page.wait_for_timeout(750)
        assert len(run_calls) <= 1, f"Expected ≤1 run request, got {len(run_calls)}"
        page.unroute("**/api/run")


class TestSseReconnection:
    """SSE stream reconnection on visibility change / resume button."""

    def test_disconnect_banner_shows_resume_button(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")

        def handle_run_drop(route):
            route.abort("connectionfailed")

        def handle_profile_status(route):
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"trained": True, "last_updated": "2025-01-01T00:00:00"}),
            )

        page.route("**/api/run", handle_run_drop)
        page.route("**/api/profile/status", handle_profile_status)
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        open_generate_section(page)
        expect(page.locator("#runBtn")).to_be_visible()
        page.locator("#runBtn").click()
        status = page.locator("#statusBox")
        expect(status).to_contain_text("Connection lost", timeout=2500)
        expect(status.locator("button")).to_contain_text("Resume")

    def test_resume_checks_run_status(self, page: Page, base_url):
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        resume_requests = []

        def handle_run_drop(route):
            route.abort("connectionfailed")

        def handle_profile_status(route):
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"trained": True, "last_updated": "2025-01-01T00:00:00"}),
            )

        def handle_run_status(route):
            resume_requests.append(route.request.url)
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"status": "completed", "tracks_found": 5}),
            )

        page.route("**/api/run", handle_run_drop)
        page.route("**/api/profile/status", handle_profile_status)
        page.route("**/api/run/*/status", handle_run_status)
        page.reload()
        page.wait_for_load_state("domcontentloaded")
        open_generate_section(page)
        expect(page.locator("#runBtn")).to_be_visible()
        page.locator("#runBtn").click()
        status = page.locator("#statusBox")
        expect(status).to_contain_text("Connection lost", timeout=2500)
        status.locator("button").click()
        page.wait_for_timeout(250)
        assert len(resume_requests) >= 1, "Resume should call /api/run/{id}/status"

