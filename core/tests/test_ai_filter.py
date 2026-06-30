"""Unit tests for core.src.ai_filter and the config FILTER_AI_ARTISTS gate."""

from __future__ import annotations

import json

import pytest

import config
from core.src import ai_filter


@pytest.fixture(autouse=True)
def _reset_blocklist():
    """Each test starts with an empty deny set (it's a module global)."""
    ai_filter._AI_ARTIST_IDS = set()
    yield
    ai_filter._AI_ARTIST_IDS = set()


# ── load_ai_blocklist ──────────────────────────────────────────────

def test_load_from_object_form(tmp_path):
    p = tmp_path / "ai_artists.json"
    p.write_text(json.dumps({"artist_ids": ["a1", "a2", "a2", ""]}), encoding="utf-8")
    n = ai_filter.load_ai_blocklist(p)
    assert n == 2  # dedup + drop empties
    assert ai_filter.ai_blocklist_available()
    assert ai_filter.ai_blocklist_size() == 2


def test_load_from_bare_list(tmp_path):
    p = tmp_path / "ai_artists.json"
    p.write_text(json.dumps(["x", "y"]), encoding="utf-8")
    assert ai_filter.load_ai_blocklist(p) == 2


def test_load_missing_file_is_noop(tmp_path):
    assert ai_filter.load_ai_blocklist(tmp_path / "nope.json") == 0
    assert not ai_filter.ai_blocklist_available()


def test_load_corrupt_file_is_noop(tmp_path):
    p = tmp_path / "ai_artists.json"
    p.write_text("{not json", encoding="utf-8")
    assert ai_filter.load_ai_blocklist(p) == 0
    assert ai_filter.ai_blocklist_size() == 0


# ── is_ai_artist / filter_ai_tracks ────────────────────────────────

def test_is_ai_artist():
    ai_filter._AI_ARTIST_IDS = {"blocked1", "blocked2"}
    assert ai_filter.is_ai_artist("blocked1")
    assert not ai_filter.is_ai_artist("clean")
    assert not ai_filter.is_ai_artist(None)
    assert not ai_filter.is_ai_artist("")


def test_filter_drops_blocked_keeps_clean():
    ai_filter._AI_ARTIST_IDS = {"ai1", "ai2"}
    tracks = [
        {"artist": "Real Band", "artist_id": "human"},
        {"artist": "Bot Act", "artist_id": "ai1"},
        {"artist": "Another", "artist_id": "ai2"},
        {"artist": "No ID", "artist_id": None},
    ]
    kept, dropped = ai_filter.filter_ai_tracks(tracks)
    assert [t["artist"] for t in kept] == ["Real Band", "No ID"]
    assert [t["artist"] for t in dropped] == ["Bot Act", "Another"]


def test_filter_is_noop_when_blocklist_empty():
    tracks = [{"artist": "X", "artist_id": "anything"}]
    kept, dropped = ai_filter.filter_ai_tracks(tracks)
    assert kept == tracks
    assert dropped == []


# ── config.get_filter_ai_artists (toggle + file gate, default off) ──

def test_getter_on_when_enabled_and_file_present(tmp_path, monkeypatch):
    p = tmp_path / "ai_artists.json"
    p.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(config, "AI_BLOCKLIST_PATH", p)
    monkeypatch.setenv("FILTER_AI_ARTISTS", "true")
    assert config.get_filter_ai_artists() is True


def test_getter_off_when_enabled_but_file_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AI_BLOCKLIST_PATH", tmp_path / "missing.json")
    monkeypatch.setenv("FILTER_AI_ARTISTS", "true")
    assert config.get_filter_ai_artists() is False


def test_getter_off_when_disabled(tmp_path, monkeypatch):
    p = tmp_path / "ai_artists.json"
    p.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(config, "AI_BLOCKLIST_PATH", p)
    monkeypatch.setenv("FILTER_AI_ARTISTS", "false")
    assert config.get_filter_ai_artists() is False


def test_getter_defaults_off_when_unset(tmp_path, monkeypatch):
    p = tmp_path / "ai_artists.json"
    p.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(config, "AI_BLOCKLIST_PATH", p)
    monkeypatch.delenv("FILTER_AI_ARTISTS", raising=False)
    # Opt-in: even with the blocklist present, the default is off.
    assert config.get_filter_ai_artists() is False
