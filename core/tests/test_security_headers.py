"""WS4 — security headers on every response (defense-in-depth)."""
from __future__ import annotations

import pytest

from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_security_headers_present(client):
    r = client.get("/api/onboarding/status")
    assert r.status_code == 200
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("Referrer-Policy") == "same-origin"


def test_security_headers_do_not_clobber_cache_header(client):
    # Static assets keep their Cache-Control AND gain the security headers.
    r = client.get("/static/js/main.js")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    if r.status_code == 200:
        assert "max-age" in (r.headers.get("Cache-Control") or "")
