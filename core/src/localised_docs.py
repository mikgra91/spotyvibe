"""Language-aware Markdown document resolver.

Provides a simple two-step fallback:
  1. Try ``<slug>.<lang>.md``
  2. Fall back to ``<slug>.en.md``
  3. Raise ``FileNotFoundError`` if English is also missing.
"""

from pathlib import Path
from config import BASE_DIR

DOC_ROOT = BASE_DIR / 'documentation'


def resolve_help(lang: str):
    """Resolve the help page for the given language."""
    return _resolve(DOC_ROOT, 'help', lang)


def resolve_guide(slug: str, lang: str):
    """Resolve a setup guide by slug and language."""
    return _resolve(DOC_ROOT / 'guides', slug, lang)


def _resolve(dir_: Path, slug: str, lang: str):
    """Return (path, served_lang, fallback_used) for the best available file."""
    primary = dir_ / f'{slug}.{lang}.md'
    if primary.is_file():
        return primary, lang, False
    english = dir_ / f'{slug}.en.md'
    if english.is_file():
        return english, 'en', (lang != 'en')
    raise FileNotFoundError(f'No document for {slug!r} in any language')

