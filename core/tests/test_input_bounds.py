"""WS2 — server-side input bounds + SSRF host guard.

- ``_sanitize_audio_filters`` drops malformed shapes (type hardening) while
  preserving valid numeric bounds (incl. BPM tempo — no wrong 0-1 clamp).
- ``_is_internal_host`` blocks private/link-local/reserved targets but
  allows loopback (local LLMs) + public hosts (custom providers).
- ``/api/llm/fetch_models`` rejects internal/private base_url with 400.
"""
from __future__ import annotations

import pytest

import app as appmod
from app import app, _sanitize_audio_filters, _is_internal_host


# ── audio filter sanitisation ────────────────────────────────────────

def test_audio_filters_non_dict_becomes_empty():
    assert _sanitize_audio_filters(None) == {}
    assert _sanitize_audio_filters([1, 2]) == {}
    assert _sanitize_audio_filters("nope") == {}


def test_audio_filters_keep_valid_numeric_bounds():
    out = _sanitize_audio_filters({"energy": {"min": 0.6, "max": 1.0}})
    assert out["energy"] == {"min": 0.6, "max": 1.0}


def test_audio_filters_tempo_bpm_not_clamped():
    out = _sanitize_audio_filters({"tempo": {"min": 120, "max": 140}})
    assert out["tempo"] == {"min": 120.0, "max": 140.0}


def test_audio_filters_drop_garbage():
    out = _sanitize_audio_filters({
        "energy": {"min": "x", "max": None},   # non-numeric → None
        "valence": "notadict",                  # dropped
        "evil_key": {"min": 1},                 # unknown key → dropped
    })
    assert out["energy"] == {"min": None, "max": None}
    assert "valence" not in out
    assert "evil_key" not in out


# ── SSRF host guard ──────────────────────────────────────────────────

@pytest.mark.parametrize("host,blocked", [
    ("10.0.0.5", True),
    ("192.168.1.1", True),
    ("172.16.0.9", True),
    ("169.254.169.254", True),   # cloud metadata
    ("127.0.0.1", False),        # loopback — local LLMs
    ("8.8.8.8", False),          # public — custom providers
    ("", False),
])
def test_is_internal_host(host, blocked):
    assert _is_internal_host(host) is blocked


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_fetch_models_blocks_internal_https(client):
    r = client.post("/api/llm/fetch_models", json={"base_url": "https://10.0.0.5"})
    assert r.status_code == 400
    assert "internal" in (r.get_json() or {}).get("error", "").lower()


def test_fetch_models_blocks_metadata(client):
    r = client.post("/api/llm/fetch_models", json={"base_url": "https://169.254.169.254"})
    assert r.status_code == 400


def test_fetch_models_existing_guards_intact(client):
    # No base_url → 400; http to a remote host → 400 (https-only).
    assert client.post("/api/llm/fetch_models", json={}).status_code == 400
    assert client.post("/api/llm/fetch_models",
                       json={"base_url": "http://example.com"}).status_code == 400
