"""Unit tests for localised document resolver (Wave 5)."""

import tempfile
from pathlib import Path
import pytest

from core.src import localised_docs


@pytest.fixture
def tmp_doc_root(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / 'guides').mkdir()
        monkeypatch.setattr(localised_docs, 'DOC_ROOT', root)
        yield root


def _write(path, text='x'):
    path.write_text(text, encoding='utf-8')


def test_help_de_exists(tmp_doc_root):
    _write(tmp_doc_root / 'help.en.md')
    _write(tmp_doc_root / 'help.de.md')
    path, lang, fallback = localised_docs.resolve_help('de')
    assert path.name == 'help.de.md'
    assert lang == 'de'
    assert fallback is False


def test_help_de_missing_falls_back_to_en(tmp_doc_root):
    _write(tmp_doc_root / 'help.en.md')
    path, lang, fallback = localised_docs.resolve_help('de')
    assert path.name == 'help.en.md'
    assert lang == 'en'
    assert fallback is True


def test_help_requested_en_not_flagged_as_fallback(tmp_doc_root):
    _write(tmp_doc_root / 'help.en.md')
    path, lang, fallback = localised_docs.resolve_help('en')
    assert fallback is False


def test_help_none_present_raises(tmp_doc_root):
    with pytest.raises(FileNotFoundError):
        localised_docs.resolve_help('de')


def test_guide_resolver_same_rules(tmp_doc_root):
    _write(tmp_doc_root / 'guides' / 'openai_api_key.en.md')
    path, lang, fallback = localised_docs.resolve_guide('openai_api_key', 'de')
    assert fallback is True
    assert lang == 'en'


def test_guide_de_exists(tmp_doc_root):
    _write(tmp_doc_root / 'guides' / 'openai_api_key.en.md')
    _write(tmp_doc_root / 'guides' / 'openai_api_key.de.md')
    path, lang, fallback = localised_docs.resolve_guide('openai_api_key', 'de')
    assert path.name == 'openai_api_key.de.md'
    assert lang == 'de'
    assert fallback is False


def test_guide_missing_both_raises(tmp_doc_root):
    with pytest.raises(FileNotFoundError):
        localised_docs.resolve_guide('nonexistent', 'en')

