"""WS1 — same-origin guard for state-changing requests.

Mutating requests from a foreign Origin/Referer must be rejected with 403
*before* any handler runs (so no state is touched). Same-origin and
loopback callers (the desktop app, tests, local browser) pass through.
GET is never blocked. Guards the credential endpoint specifically.
"""
from __future__ import annotations

import pytest

from app import app

MUTATING = ["/api/settings/credentials", "/api/feedback", "/api/save-profile"]


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.mark.parametrize("path", MUTATING)
def test_foreign_origin_blocked(client, path):
    r = client.post(path, json={}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403


@pytest.mark.parametrize("path", MUTATING)
def test_foreign_referer_blocked(client, path):
    # No Origin, only a cross-site Referer → still blocked.
    r = client.post(path, json={}, headers={"Referer": "http://evil.example/x"})
    assert r.status_code == 403


@pytest.mark.parametrize("path", MUTATING)
def test_same_origin_passes_guard(client, path):
    # localhost Origin matching the test host → guard passes (handler may
    # 400 on an empty body, but must NOT be 403).
    r = client.post(path, json={}, headers={"Origin": "http://localhost"})
    assert r.status_code != 403


def test_loopback_origin_any_port_allowed(client):
    # Desktop / dynamic-port case: 127.0.0.1 on a different port is loopback.
    r = client.post("/api/feedback", json={},
                    headers={"Origin": "http://127.0.0.1:9999"})
    assert r.status_code != 403


def test_missing_origin_and_referer_allowed_on_loopback(client):
    # Native/same-origin caller with neither header, host is loopback → allow.
    r = client.post("/api/feedback", json={})
    assert r.status_code != 403


def test_get_not_blocked_even_cross_origin(client):
    r = client.get("/api/onboarding/status", headers={"Origin": "http://evil.example"})
    assert r.status_code != 403


def test_block_happens_before_handler_no_state(client):
    # A blocked credential write must return 403, not reach save logic.
    r = client.post("/api/settings/credentials",
                    json={"openai_api_key": "sk-evil"},
                    headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
    body = r.get_json() or {}
    assert "error" in body
