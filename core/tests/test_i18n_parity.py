"""i18n locale parity test.

Guarantees that ``frontend/static/i18n/en.json``, ``de.json`` and ``jp.json``
expose the **same set of keys**. A missing key in one locale leaves part of
the UI untranslated; a stale key in one locale shows up as a typo nobody
notices until a user reports it.

Referenced from ``documentation/TechnicalManual.md`` (line ~191).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

I18N_DIR = Path(__file__).resolve().parents[2] / "frontend" / "static" / "i18n"
LOCALES = ("en", "de", "jp")


def _load(locale: str) -> dict:
    return json.loads((I18N_DIR / f"{locale}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def locale_keys() -> dict[str, set[str]]:
    return {loc: set(_load(loc).keys()) for loc in LOCALES}


def test_all_locales_have_identical_key_sets(locale_keys):
    en = locale_keys["en"]
    for other in ("de", "jp"):
        missing = sorted(en - locale_keys[other])
        extra = sorted(locale_keys[other] - en)
        assert not missing and not extra, (
            f"Locale '{other}' is out of sync with 'en':\n"
            f"  missing in {other}: {missing}\n"
            f"  extra in {other}:   {extra}"
        )


def test_no_empty_translation_values():
    """Empty strings indicate a forgotten translation, not a deliberate
    blank — flag them so they don't slip into a release."""
    for loc in LOCALES:
        data = _load(loc)
        empty = sorted(k for k, v in data.items() if isinstance(v, str) and not v.strip())
        assert not empty, f"Locale '{loc}' has empty translations for: {empty}"

