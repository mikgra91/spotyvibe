"""WS7 — pin path-traversal safety + run-state lifecycle (regression).

No production code change; these tests guard existing behavior so a
future refactor can't silently reintroduce a traversal hole or a run-map
leak / cancel crash.
"""
from __future__ import annotations

import threading
import time

import pytest

import app as appmod
from app import app

TRAVERSALS = [
    "../../config.py",
    "..%2f..%2fconfig.py",
    "....//....//config.py",
    "..\\..\\config.py",
]


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.mark.parametrize("base", ["/docs/screenshots/", "/docs/guides/"])
@pytest.mark.parametrize("evil", TRAVERSALS)
def test_doc_routes_block_traversal(client, base, evil):
    r = client.get(base + evil)
    assert r.status_code in (400, 403, 404)            # never served
    assert b"def get_or_create_secret_key" not in r.data  # no config.py leak


# ── run-state lifecycle ──────────────────────────────────────────────

def test_sweep_stale_runs_removes_old_keeps_fresh():
    with appmod._runs_lock:
        appmod._runs.clear()
        appmod._runs["old"] = {"cancel": threading.Event(), "finalize_on_cancel": False,
                               "verified_tracks": [], "created_at": time.monotonic() - 10_000}
        appmod._runs["fresh"] = {"cancel": threading.Event(), "finalize_on_cancel": False,
                                 "verified_tracks": [], "created_at": time.monotonic()}
    try:
        appmod._sweep_stale_runs()
        assert "old" not in appmod._runs
        assert "fresh" in appmod._runs
    finally:
        with appmod._runs_lock:
            appmod._runs.clear()


def test_cancel_run_sets_event_and_is_idempotent(client):
    ev = threading.Event()
    with appmod._runs_lock:
        appmod._runs["r1"] = {"cancel": ev, "finalize_on_cancel": False,
                              "verified_tracks": [], "created_at": time.monotonic()}
    try:
        r1 = client.post("/api/cancel", json={"run_id": "r1", "finalize": True})
        assert r1.get_json()["status"] == "ok"
        assert ev.is_set()
        assert appmod._runs["r1"]["finalize_on_cancel"] is True
        # Double-cancel must not raise; run still present → ok again.
        r2 = client.post("/api/cancel", json={"run_id": "r1"})
        assert r2.get_json()["status"] == "ok"
        # Unknown run → graceful not_found, never 500.
        r3 = client.post("/api/cancel", json={"run_id": "nope"})
        assert r3.get_json()["status"] == "not_found"
    finally:
        with appmod._runs_lock:
            appmod._runs.clear()
