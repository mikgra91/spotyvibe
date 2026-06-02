"""API robustness — malformed request bodies must yield 400, never 500.

Regression guard for the 2026-06-01 hardening: endpoints that read
``request.get_json(force=True)`` then call ``data.get(...)`` used to crash
with AttributeError → HTTP 500 when the body was valid JSON of the wrong
type (null / list / number / string), or silently 200 on garbage
(/api/settings). They now reject any non-object body with 400 via
``_request_json_object()``.

This is the kind of "basic issue" we want caught automatically before
manual testing. Add new input-parsing endpoints here as they appear.
"""

from __future__ import annotations

import pytest

from app import app

# (method, path) for endpoints that parse a JSON object body.
ENDPOINTS = [
    ("POST", "/api/feedback"),
    ("POST", "/api/feedback/dislike-artist"),
    ("POST", "/api/remove"),
    ("POST", "/api/settings"),
    ("POST", "/api/settings/credentials"),
    ("POST", "/api/train-profile"),
    ("POST", "/api/save-profile"),
    ("POST", "/api/songlist"),
    ("DELETE", "/api/songlist/track"),
]

# Bodies that are NOT a JSON object. Each must be rejected with 400 — and
# crucially must crash before any storage write, so this never mutates state.
MALFORMED_BODIES = [
    b"",            # empty
    b"not json",    # invalid JSON
    b"null",        # JSON null
    b"[]",          # JSON array
    b"123",         # JSON number
    b'"x"',         # JSON string
]


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.mark.parametrize("method,path", ENDPOINTS)
@pytest.mark.parametrize("body", MALFORMED_BODIES)
def test_wrong_type_body_returns_400_not_500(client, method, path, body):
    resp = client.open(path, method=method, data=body, content_type="application/json")
    assert resp.status_code == 400, (
        f"{method} {path} with body {body!r} returned {resp.status_code}, "
        f"expected 400 (must not 500 or silently 200 on non-object bodies)"
    )
