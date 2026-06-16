"""WS5 — secret key persistence + credential masking hygiene.

- FLASK_SECRET_KEY is stable across app restarts (persisted, not random
  per-start) so sessions survive a relaunch.
- The credentials GET contract returns only masked values + is_set flags,
  never plaintext secret material.
"""
from __future__ import annotations

import config


def test_secret_key_env_override(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "supersecret-env")
    assert config.get_or_create_secret_key() == b"supersecret-env"


def test_secret_key_persisted_and_stable(monkeypatch, tmp_path):
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
    key_file = tmp_path / ".flask_secret"
    monkeypatch.setattr(config, "SECRET_KEY_FILE", key_file)
    k1 = config.get_or_create_secret_key()
    k2 = config.get_or_create_secret_key()
    assert k1 == k2                       # stable across "restarts"
    assert key_file.exists()
    assert len(k1) >= 16                  # not a trivial key


def test_credentials_get_is_masked(monkeypatch, tmp_path):
    # Force the dotenv fallback path with a controlled secret value.
    cred_file = tmp_path / ".credentials"
    key = config.CREDENTIALS_KEYS[0]
    secret = "sk-ABCDEF1234567890SECRET"
    cred_file.write_text(f"{key}={secret}\n", encoding="utf-8")
    monkeypatch.setattr(config, "CREDENTIALS_FILE", cred_file)
    monkeypatch.setattr(config, "_KEYRING_AVAILABLE", False)

    out = config.get_credentials()
    entry = out[key]
    assert entry["is_set"] is True
    assert entry["masked"].endswith(secret[-4:])      # shows last 4 only
    assert secret not in entry["masked"]               # never full plaintext
    assert set(entry.keys()) == {"masked", "is_set"}   # no raw 'value' field
