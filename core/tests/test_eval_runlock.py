"""Tests for the evaluation run-lock helper."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# Lock helper lives under evaluation/, which isn't on sys.path during
# normal test runs — add it manually.
import sys
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from evaluation._runlock import (  # noqa: E402
    LockHeldError,
    acquire,
    release_stale_lock,
)


@pytest.fixture
def lock_path(tmp_path: Path) -> Path:
    return tmp_path / ".run.lock"


def test_acquire_creates_lock_file_with_metadata(lock_path):
    release = acquire(lock_path, kind="evaluation")
    try:
        assert lock_path.exists()
        meta = json.loads(lock_path.read_text(encoding="utf-8"))
        assert meta["pid"] == os.getpid()
        assert meta["kind"] == "evaluation"
        assert "started_at" in meta and "host" in meta
    finally:
        release()


def test_release_removes_lock_file(lock_path):
    release = acquire(lock_path, kind="evaluation")
    assert lock_path.exists()
    release()
    assert not lock_path.exists()


def test_double_release_is_safe(lock_path):
    release = acquire(lock_path, kind="evaluation")
    release()
    # Calling release a second time must not raise even though the file is gone.
    release()
    assert not lock_path.exists()


def test_second_acquire_raises_lock_held(lock_path):
    release = acquire(lock_path, kind="evaluation")
    try:
        with pytest.raises(LockHeldError) as excinfo:
            acquire(lock_path, kind="evaluation")
        # Error message must name the holder PID so the user can act.
        assert str(os.getpid()) in str(excinfo.value)
        assert "evaluation" in str(excinfo.value)
    finally:
        release()


def test_release_stale_lock_removes_existing_file(lock_path):
    lock_path.write_text("{}", encoding="utf-8")
    assert release_stale_lock(lock_path) is True
    assert not lock_path.exists()


def test_release_stale_lock_returns_false_when_missing(lock_path):
    assert release_stale_lock(lock_path) is False


def test_acquire_after_stale_release_succeeds(lock_path):
    # Simulate a hard-killed previous run (lock file left behind).
    lock_path.write_text(
        json.dumps({"pid": 999999, "kind": "evaluation", "host": "ghost",
                    "started_at": "2026-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    # Fresh acquire must fail (we don't auto-steal).
    with pytest.raises(LockHeldError):
        acquire(lock_path, kind="evaluation")
    # User runs --release-lock, then retries → succeeds.
    assert release_stale_lock(lock_path) is True
    release = acquire(lock_path, kind="evaluation")
    try:
        assert lock_path.exists()
    finally:
        release()

