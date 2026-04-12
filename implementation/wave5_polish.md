# Wave 5 — Polish: help-page language support, remaining setup guides, DE translations

> **Reader.** This document is written for Claude Sonnet 4.6 to implement. It assumes no memory of prior conversations. It is self-contained.
>
> **Prerequisites.** Waves 1, 2, 3, 4 must be merged first. Wave 5 finishes three loose ends from earlier waves:
> - The **help page** is still English-only (flagged in Wave-1 § A.3 and Wave-4's scope fence).
> - Two setup guides — **G3 (Python on macOS)** and **G4 (Python on Linux)** — were deferred from Wave 1.
> - The four setup guides (G1–G4) have **no German translations** yet; Wave 1 deliberately shipped English text around English-only screenshots.
>
> **Source of truth for *why*.** [`../design.md`](../design.md) § F.2 and § A.3 (the deferred guides).
>
> **Working directory.** `c:\git\spotyvibe`. All paths below are relative to the repo root.
>
> **Conventions.** Vanilla ES modules, no bundler. Jinja2 templates. Modular CSS. i18n via `data-i18n` + `i18n(key, fallback)`. Markdown content is localised by **separate files**, not key-based translation. See [`../CLAUDE.md`](../CLAUDE.md).
>
> **What this wave is.** No new UX — just completion. After Wave 5, a German-locale user sees the entire app (including long-form help) in their language, with a graceful fallback to English only where a section genuinely hasn't been translated.
>
> **What this wave is NOT.** No new features. No visual polish. No performance work. No Android/APK-specific voice support. No native Anthropic/Gemini SDKs. If you're about to add a new surface, stop.

---

## 1. Scope map

| Ref | Name | Summary |
|-----|------|---------|
| F.2 | Help page language support | Split `documentation/help.md` into `help.en.md` and `help.de.md`. The `/api/help` endpoint reads the UI-language session value and serves the matching file, falling back to English when the DE file is absent or a section is untranslated. When falling back, the help modal shows a subtle banner: "This section isn't translated yet." |
| A.3 (finish) | Setup guides G3, G4 | Ship the two install guides deferred from Wave 1: "Install Python and launch SpotyVibe on macOS" and "… on Linux". Same format as G1/G2: YAML frontmatter + numbered steps + per-step screenshots + optional copy-pill. |
| A.3 (i18n) | DE translations for guides | Produce `*.de.md` variants for all four guides (G1, G2, G3, G4). **Screenshots stay English** — the Wave-1 decision stands: shipping DE screenshots doubles maintenance burden for marginal win. Text around screenshots is localised. |

---

## 2. Files to create, modify, delete

### Create

| Path | Purpose |
|------|---------|
| `documentation/help.de.md` | German translation of the entire help page. |
| `documentation/guides/openai_api_key.de.md` | G1 German translation. |
| `documentation/guides/spotify_developer_app.de.md` | G2 German translation. |
| `documentation/guides/python_install_macos.en.md` | G3 (new) — English. |
| `documentation/guides/python_install_macos.de.md` | G3 — German. |
| `documentation/guides/python_install_linux.en.md` | G4 (new) — English. |
| `documentation/guides/python_install_linux.de.md` | G4 — German. |
| `documentation/assets/guides/python-macos/*.png` | G3 step screenshots (placeholder 1×1 PNGs; implementer replaces by manual capture). |
| `documentation/assets/guides/python-linux/*.png` | G4 step screenshots (placeholders). |
| `implementation/wave5_polish.md` | **This file.** |

### Rename / split

| From | To | Notes |
|------|-----|-------|
| `documentation/help.md` | `documentation/help.en.md` | Git-rename. Preserves history. After the rename the file's content stays identical — the split *is* the rename on the English side. Do not also keep `help.md` as a stub (the endpoint is updated to resolve `help.{lang}.md`). |

### Modify

| Path | What changes |
|------|--------------|
| `app.py` | Language-aware help resolver (see § 4). Guide slug whitelist expanded to include `python_install_macos`, `python_install_linux`. Add `section_translated` field per-section in the response when relevant. |
| `frontend/templates/modals/help_modal.html` | Add banner DOM (initially hidden). |
| `frontend/static/js/modules/help.js` (or wherever the help modal renders) | Show the banner when the server indicates a fallback. |
| `frontend/static/css/modals.css` | Style for the help banner (`.help-fallback-banner`). |
| `frontend/static/i18n/en.json` | Add every key listed in § 8. |
| `frontend/static/i18n/de.json` | Same keys, German strings. |
| `documentation/UserManual.md` | Note the language-aware help and the two new guides. |
| `documentation/TechnicalManual.md` | Note the help resolver's fallback contract. |
| `documentation/assets/guides/README.md` | Add G3, G4 entries and note the `.de.md` filename convention. |
| `onboarding.html` (Wave 1) | If the onboarding credentials-step "Read full guide" buttons are only shown for G1/G2 today, leave them alone. If the help modal has a guide-index surface (it shouldn't in current code; verify), add G3/G4 links there. |
| `frontend/tests/test_documentation_screenshots.py` | Screenshots 93–99 (see § 9). |
| `frontend/tests/test_frontend.py` | 4 smoke tests (see § 10). |

### Delete

Nothing. `help.md` is renamed, not deleted.

---

## 3. Shared pattern — language-aware markdown resolver (contract)

A single contract drives both the help endpoint and the existing guide endpoint added in Wave 1:

```
resolve(slug: str, lang: str) -> (absolute_path: Path, matched_lang: str, fallback_used: bool)
```

- Try `documentation/<dir>/<slug>.<lang>.md`.
- If missing, try `documentation/<dir>/<slug>.en.md`; set `fallback_used=True`.
- If English is also missing, raise `FileNotFoundError` (caller returns 404).

For the help page specifically, `<dir>` is `documentation/` and `<slug>` is `help`. For guides, `<dir>` is `documentation/guides/` and `<slug>` is the guide's id (e.g. `openai_api_key`).

Centralise this in a small helper in `app.py` or in a new `core/src/localised_docs.py` module — either works. Bias toward `core/src/localised_docs.py` for testability; the function is a one-liner but pure.

---

## 4. F.2 — Help page language support

### 4.1 Endpoint behaviour

`GET /api/help` (existing):

- Reads the session language via whatever mechanism the app currently uses (`get_ui_language()` or similar; Wave 1 introduced this contract with the `ui_language` setting).
- Resolves `help.{lang}.md` via § 3.
- Returns `{ html, fallback_used: bool, requested_lang: str, served_lang: str }`.
- `html` is the rendered Markdown → HTML (keep the existing renderer).
- When `fallback_used=True`, the client shows the banner.

This is a **whole-document** fallback. Per-section fallback is out of scope for this wave. Reasoning: it adds parsing complexity and is not required by the design — a DE translation either exists for the whole help document or it doesn't. The "Some sections aren't translated" nuance from design.md F.2 is handled by ensuring `help.de.md` exists as a complete document; if a paragraph is missing a translation, leave the English paragraph in place (translators will see it and can fix it).

### 4.2 Help-modal DOM change

Add to `help_modal.html`, immediately inside the modal body, above the existing `#helpContent`:

```html
<div class="help-fallback-banner hidden" id="helpFallbackBanner" role="status" aria-live="polite">
  <span class="help-fallback-icon" aria-hidden="true">🌐</span>
  <span class="help-fallback-text" data-i18n="help.fallback_banner">This page isn't translated yet. Showing English.</span>
  <button class="help-fallback-close" onclick="dismissHelpBanner()" aria-label="Dismiss" data-i18n-title="help.fallback_dismiss_title" title="Dismiss">✕</button>
</div>
```

### 4.3 Banner styling (add to `modals.css`)

```
.help-fallback-banner {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 10px 14px;
  background: rgba(245,158,11,0.08);
  border: 1px solid rgba(245,158,11,0.25);
  border-radius: var(--radius-md);
  margin-bottom: 16px;
  font-size: 0.85rem;
  color: var(--text-secondary);
}
.help-fallback-icon { font-size: 1rem; flex-shrink: 0; }
.help-fallback-text { flex: 1; }
.help-fallback-close {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 0.9rem;
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  transition: color 150ms, background 150ms;
}
.help-fallback-close:hover { color: var(--text-primary); background: rgba(255,255,255,0.06); }
```

### 4.4 Client-side behaviour

In whichever module fetches help content (likely in `modals.js` or a dedicated `help.js`):

```js
async function loadHelpContent() {
  const res = await fetch('/api/help');
  const data = await res.json();
  document.getElementById('helpContent').innerHTML = data.html;
  const banner = document.getElementById('helpFallbackBanner');
  if (data.fallback_used) {
    banner.classList.remove('hidden');
  } else {
    banner.classList.add('hidden');
  }
}

function dismissHelpBanner() {
  document.getElementById('helpFallbackBanner').classList.add('hidden');
}
```

The banner is session-scoped (not persisted). Each modal open re-queries and re-renders. This is correct: if the user switches language mid-session, the next help open reflects the new state without special handling.

### 4.5 Section-help overlay

`base.html` also contains a separate `#sectionHelpOverlay` (scrolls help to a specific section). It uses the same `/api/help` payload; the same banner applies. Insert an equivalent banner DOM into the section-help wrapper and reuse the same dismiss handler.

---

## 5. G3 — Install Python and launch SpotyVibe on macOS

### 5.1 Content outline (`documentation/guides/python_install_macos.en.md`)

```markdown
---
title: Install Python and launch SpotyVibe on macOS
subtitle: The app runs in your browser; you just need Python once.
---

## Step 1 — Check if Python is already installed
Open the Terminal app (Finder → Applications → Utilities → Terminal, or press ⌘Space and type "Terminal"). Type this and press Enter:

```copy
python3 --version
```

If you see a version number like `Python 3.11.4`, skip to Step 3. If you see "command not found", continue with Step 2.

![Terminal showing Python version check](/docs/guides/python-macos/step1_check.png)

## Step 2 — Install Python with the official installer
Download the latest macOS Python installer from [python.org/downloads/macos](https://www.python.org/downloads/macos/). Open the `.pkg` file you just downloaded and follow the installer. When it finishes, re-run the check from Step 1 to confirm.

![Python installer on macOS](/docs/guides/python-macos/step2_installer.png)

## Step 3 — Install SpotyVibe
Back in the Terminal, type this to install the SpotyVibe wheel. Replace `spotyvibe-*.whl` with the file name of the wheel you downloaded:

```copy
pip3 install spotyvibe-*.whl
```

If `pip3 install` fails with a permission error, try `pip3 install --user spotyvibe-*.whl`.

![pip install succeeding](/docs/guides/python-macos/step3_install.png)

## Step 4 — Launch SpotyVibe
Type `spotyvibe` and press Enter. A browser tab opens at `http://127.0.0.1:5000` with the app ready. Leave the Terminal window open while you use the app — closing it stops SpotyVibe.

```copy
spotyvibe
```

![SpotyVibe running in Terminal and browser](/docs/guides/python-macos/step4_launch.png)
```

### 5.2 Screenshot assets

Create placeholder 1×1 transparent PNGs at the four paths referenced above. Annotate in `documentation/assets/guides/README.md` that these are placeholders to be replaced by manual capture on macOS.

### 5.3 German translation (`python_install_macos.de.md`)

Same structure, translated prose. Keep all code blocks (`python3 --version`, `pip3 install spotyvibe-*.whl`, `spotyvibe`), URLs, and image paths verbatim — only human-readable prose is translated.

Draft German strings for the implementer to refine:

- Title: "Python installieren und SpotyVibe unter macOS starten"
- Subtitle: "Die App läuft in deinem Browser; du brauchst Python nur einmal zu installieren."
- Step 1 title: "Prüfen, ob Python bereits installiert ist"
- Step 2 title: "Python mit dem offiziellen Installer installieren"
- Step 3 title: "SpotyVibe installieren"
- Step 4 title: "SpotyVibe starten"

Keep paragraph lengths comparable to English.

---

## 6. G4 — Install Python and launch SpotyVibe on Linux

### 6.1 Content outline (`documentation/guides/python_install_linux.en.md`)

```markdown
---
title: Install Python and launch SpotyVibe on Linux
subtitle: Most distros already have Python; this confirms it and installs SpotyVibe.
---

## Step 1 — Check Python
Open a terminal. On Ubuntu/Debian/Fedora/Arch, Python 3 is usually pre-installed. Confirm:

```copy
python3 --version
```

You need Python **3.10 or newer**. If your version is older, or Python is missing, continue with Step 2.

![Terminal showing python version](/docs/guides/python-linux/step1_check.png)

## Step 2 — Install Python (if needed)
Use your distro's package manager. Pick the command for your distro:

```copy
# Ubuntu / Debian
sudo apt update && sudo apt install -y python3 python3-pip python3-venv

# Fedora
sudo dnf install -y python3 python3-pip

# Arch
sudo pacman -S python python-pip
```

## Step 3 — Create a virtual environment (recommended)
System-wide `pip install` is blocked on many modern distros. Use a virtual environment:

```copy
python3 -m venv ~/.spotyvibe-venv
source ~/.spotyvibe-venv/bin/activate
```

Your prompt now starts with `(.spotyvibe-venv)`. All `pip` and `spotyvibe` commands below run inside this venv.

## Step 4 — Install SpotyVibe
Replace `spotyvibe-*.whl` with the file name of the wheel you downloaded:

```copy
pip install spotyvibe-*.whl
```

![pip install succeeding](/docs/guides/python-linux/step2_install.png)

## Step 5 — Launch SpotyVibe
With the venv still active:

```copy
spotyvibe
```

A browser tab opens at `http://127.0.0.1:5000`. Leave the terminal window open while using the app.

Next time you start the app, remember to activate the venv again first:

```copy
source ~/.spotyvibe-venv/bin/activate
spotyvibe
```

![SpotyVibe running](/docs/guides/python-linux/step3_launch.png)
```

### 6.2 Screenshot assets

Three placeholder PNGs under `documentation/assets/guides/python-linux/`.

### 6.3 German translation (`python_install_linux.de.md`)

Same structure, German prose. Keep all shell commands verbatim. Distro labels ("Ubuntu / Debian", "Fedora", "Arch") stay in English — they're proper nouns.

---

## 7. Backend changes — `app.py`

### 7.1 Help endpoint

```python
from core.src.localised_docs import resolve_help

@app.route('/api/help', methods=['GET'])
def api_help():
    lang = get_ui_language() or 'en'
    path, served_lang, fallback_used = resolve_help(lang)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            markdown_text = f.read()
    except FileNotFoundError:
        return jsonify({'error': 'help_not_found'}), 404
    html = render_markdown(markdown_text)
    return jsonify({
        'html': html,
        'requested_lang': lang,
        'served_lang': served_lang,
        'fallback_used': fallback_used,
    })
```

### 7.2 Guide slug whitelist

In the Wave-1 `GET /api/help/guide/<slug>` route, expand the whitelist from `{"openai_api_key", "spotify_developer_app"}` to include `{"python_install_macos", "python_install_linux"}`. Reuse the same resolver pattern (§ 3).

### 7.3 Resolver module (`core/src/localised_docs.py`)

```python
from pathlib import Path

DOC_ROOT = Path(__file__).resolve().parent.parent.parent / 'documentation'

def resolve_help(lang: str):
    return _resolve(DOC_ROOT, 'help', lang)

def resolve_guide(slug: str, lang: str):
    return _resolve(DOC_ROOT / 'guides', slug, lang)

def _resolve(dir_: Path, slug: str, lang: str):
    primary = dir_ / f'{slug}.{lang}.md'
    if primary.is_file():
        return primary, lang, False
    english = dir_ / f'{slug}.en.md'
    if english.is_file():
        return english, 'en', (lang != 'en')
    raise FileNotFoundError(f'No document for {slug!r} in any language')
```

Unit tests for this module live in `core/tests/test_localised_docs.py` (create):

- Existing DE file → returned as primary with `fallback_used=False`.
- Missing DE, existing EN → returned with `fallback_used=True`, `served_lang='en'`.
- Missing DE and EN → raises `FileNotFoundError`.
- Requested language is already `en` → `fallback_used=False` even though the path uses `.en.md`.

---

## 8. i18n keys

Append to `en.json` and `de.json`.

```
# Help fallback banner (F.2)
help.fallback_banner           = "This page isn't translated yet. Showing English." / "Diese Seite ist noch nicht übersetzt. Englische Version wird angezeigt."
help.fallback_dismiss_title    = "Dismiss"                                          / "Schließen"
help.language_indicator        = "Language: {lang}"                                 / "Sprache: {lang}"
```

No other i18n additions needed — the guide slug whitelist change and the resolver do not surface new UI strings.

---

## 9. Screenshot tests — additions to `test_documentation_screenshots.py`

Numbers 93–99. Append after Wave 4.

```python
# -- Wave 5: Polish ---------------------------------------------------

def test_93_help_modal_en(self, page: Page, screenshot_url):
    """Screenshot: Help modal in English."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
    page.wait_for_timeout(200)
    page.locator("button:has-text('Help')").click()
    page.wait_for_timeout(500)
    _shot_element(page, "93_help_modal_en", "#helpModal .modal")

def test_94_help_modal_de(self, page: Page, screenshot_url):
    """Screenshot: Help modal served in German (DE file present)."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    # Force UI language to de
    page.evaluate("localStorage.setItem('svLang', 'de')")
    page.reload()
    page.wait_for_load_state("networkidle")
    page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
    page.wait_for_timeout(200)
    page.locator("button:has-text('Hilfe'), button:has-text('Help')").first.click()
    page.wait_for_timeout(500)
    _shot_element(page, "94_help_modal_de", "#helpModal .modal")

def test_95_help_fallback_banner(self, page: Page, screenshot_url):
    """Screenshot: Help modal with fallback banner visible (simulated)."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    # Intercept /api/help to force fallback_used=true
    def handle(route):
        route.fulfill(
            status=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "html": "<h2>About SpotyVibe</h2><p>...</p>",
                "requested_lang": "de",
                "served_lang": "en",
                "fallback_used": True,
            }),
        )
    page.route("**/api/help", handle)
    page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
    page.wait_for_timeout(200)
    page.locator("button:has-text('Help'), button:has-text('Hilfe')").first.click()
    page.wait_for_timeout(500)
    _shot_element(page, "95_help_fallback_banner", "#helpModal .modal")

def test_96_guide_python_macos_overlay(self, page: Page, screenshot_url):
    """Screenshot: Python-install-macOS guide overlay (English)."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.evaluate("""() => {
        import('/static/js/modules/setup_guide.js').then(SG => {
            SG.openSetupGuide('python_install_macos');
        });
    }""")
    page.wait_for_timeout(700)
    _shot(page, "96_guide_python_macos_overlay")

def test_97_guide_python_linux_overlay(self, page: Page, screenshot_url):
    """Screenshot: Python-install-Linux guide overlay (English)."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.evaluate("""() => {
        import('/static/js/modules/setup_guide.js').then(SG => {
            SG.openSetupGuide('python_install_linux');
        });
    }""")
    page.wait_for_timeout(700)
    _shot(page, "97_guide_python_linux_overlay")

def test_98_guide_openai_overlay_de(self, page: Page, screenshot_url):
    """Screenshot: OpenAI setup guide overlay in German."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.evaluate("localStorage.setItem('svLang', 'de')")
    page.reload()
    page.wait_for_load_state("networkidle")
    page.evaluate("""() => {
        import('/static/js/modules/setup_guide.js').then(SG => {
            SG.openSetupGuide('openai_api_key');
        });
    }""")
    page.wait_for_timeout(700)
    _shot(page, "98_guide_openai_overlay_de")

def test_99_guide_spotify_overlay_de(self, page: Page, screenshot_url):
    """Screenshot: Spotify setup guide overlay in German."""
    page.goto(screenshot_url)
    page.wait_for_load_state("networkidle")
    page.evaluate("localStorage.setItem('svLang', 'de')")
    page.reload()
    page.wait_for_load_state("networkidle")
    page.evaluate("""() => {
        import('/static/js/modules/setup_guide.js').then(SG => {
            SG.openSetupGuide('spotify_developer_app');
        });
    }""")
    page.wait_for_timeout(700)
    _shot(page, "99_guide_spotify_overlay_de")
```

---

## 10. Smoke tests — additions to `test_frontend.py`

```python
def test_help_served_in_english_by_default(page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
    page.locator("button:has-text('Help')").click()
    page.wait_for_selector("#helpContent")
    # Banner should NOT be visible for EN request against EN content
    assert page.locator("#helpFallbackBanner").is_hidden()

def test_help_served_in_german_when_de_present(page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.evaluate("localStorage.setItem('svLang', 'de')")
    page.reload()
    page.wait_for_load_state("networkidle")
    page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
    page.locator("button").filter(has_text="Hilfe").or_(page.locator("button").filter(has_text="Help")).first.click()
    page.wait_for_selector("#helpContent")
    # No fallback expected — help.de.md exists
    assert page.locator("#helpFallbackBanner").is_hidden()

def test_help_fallback_banner_appears(page, base_url):
    """Simulate a server returning fallback_used=true and assert the banner renders."""
    page.route("**/api/help", lambda r: r.fulfill(
        status=200,
        headers={"Content-Type": "application/json"},
        body=json.dumps({
            "html": "<p>hello</p>",
            "requested_lang": "de",
            "served_lang": "en",
            "fallback_used": True,
        }),
    ))
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.locator(".burger-btn[aria-controls='settingsDropdown']").click()
    page.locator("button:has-text('Help'), button:has-text('Hilfe')").first.click()
    page.wait_for_selector("#helpFallbackBanner:not(.hidden)")
    page.locator(".help-fallback-close").click()
    assert page.locator("#helpFallbackBanner").is_hidden()

def test_guide_whitelist_accepts_new_slugs(page, base_url):
    """Python install guides return 200 via the guide endpoint."""
    responses = {}
    def track(slug):
        def handler(route):
            responses[slug] = True
            route.continue_()
        return handler
    page.route("**/api/help/guide/python_install_macos", track('macos'))
    page.route("**/api/help/guide/python_install_linux", track('linux'))
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.evaluate("fetch('/api/help/guide/python_install_macos').then(r => r.json())")
    page.evaluate("fetch('/api/help/guide/python_install_linux').then(r => r.json())")
    page.wait_for_timeout(400)
    assert responses.get('macos') is True
    assert responses.get('linux') is True
```

---

## 11. Backend unit tests — `core/tests/test_localised_docs.py`

```python
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

def _write(path: Path, text: str = 'x'):
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
```

---

## 12. Acceptance checklist

- [ ] `documentation/help.md` has been git-renamed to `documentation/help.en.md`. Git history is preserved (commit with `git mv`).
- [ ] `documentation/help.de.md` exists and is a complete German translation of the English version.
- [ ] `/api/help` returns the German document when UI language is `de` and `help.de.md` exists. `fallback_used=false` in that case.
- [ ] `/api/help` returns the English document with `fallback_used=true` when UI language is `de` and DE file is absent.
- [ ] `/api/help` returns `fallback_used=false` when UI language is `en`, regardless of whether a DE file exists.
- [ ] `#helpFallbackBanner` shows exactly when `fallback_used=true`, hides otherwise.
- [ ] Dismiss (✕) hides the banner without persisting state; next modal open re-queries and may re-show it.
- [ ] Banner styling matches § 4.3 (amber-tinted, icon + text + dismiss).
- [ ] `#sectionHelpOverlay` has an equivalent banner wired to the same content flow.
- [ ] G3 (`python_install_macos.en.md`) and G4 (`python_install_linux.en.md`) exist with 4 and 5 steps respectively, including at least one ```` ```copy ```` block each.
- [ ] G3.de.md and G4.de.md are present and complete.
- [ ] G1.de.md and G2.de.md are present and complete.
- [ ] `/api/help/guide/python_install_macos` returns 200 with parsed frontmatter + steps.
- [ ] `/api/help/guide/python_install_linux` returns 200 with parsed frontmatter + steps.
- [ ] Unknown slugs still 404.
- [ ] All four guides served in DE when `ui_language=de` and `.de.md` present.
- [ ] All four guides fall back to EN with `fallback_used=true` when `.de.md` absent (this is not expected post-Wave-5 but the resolver must still handle it).
- [ ] Screenshots in DE guides reference the same image paths as EN (English screenshots shared across languages).
- [ ] Placeholder PNGs exist at every referenced image path for G3 and G4 (so overlays do not 404).
- [ ] `documentation/assets/guides/README.md` updated with G3/G4 entries and a note about the `.de.md` naming convention.
- [ ] All 4 smoke tests (§ 10) pass.
- [ ] All 7 new screenshot tests (§ 9) pass under `-m screenshots`.
- [ ] All new backend unit tests (§ 11) pass.
- [ ] No existing test regresses — full suite passes.
- [ ] No hardcoded English in any new template or JS.
- [ ] `documentation/UserManual.md` notes the language-aware help.
- [ ] `documentation/TechnicalManual.md` documents the resolver fallback contract.

---

## 13. Review checklist before merging

- [ ] `version.py` bumped.
- [ ] Project-tree section of `CLAUDE.md` updated: `help.en.md`, `help.de.md`, guides directory expanded.
- [ ] No post-Wave-5 surfaces started — this is the last scheduled wave.
- [ ] All new strings exist in both `en.json` and `de.json`.
- [ ] G1/G2 DE translations reviewed by a German-speaking reviewer (or AI pass) for technical correctness — copying a literal English translation is not acceptable for terminology like "API key", "Redirect URI", "Client Secret" (these stay in English because they're field names in external dashboards, but surrounding prose must be natural German).
- [ ] Privacy modal (Wave 1) — verify the data-flow table is identical in `help.de.md`.

---

## 14. Reference — surfaces you will touch in Wave 5

| File | Action |
|------|--------|
| `documentation/help.md` | Git-rename → `documentation/help.en.md` |
| `documentation/help.de.md` | Create — full German translation |
| `documentation/guides/openai_api_key.de.md` | Create |
| `documentation/guides/spotify_developer_app.de.md` | Create |
| `documentation/guides/python_install_macos.en.md` | Create |
| `documentation/guides/python_install_macos.de.md` | Create |
| `documentation/guides/python_install_linux.en.md` | Create |
| `documentation/guides/python_install_linux.de.md` | Create |
| `documentation/assets/guides/python-macos/*.png` | Create — placeholders |
| `documentation/assets/guides/python-linux/*.png` | Create — placeholders |
| `documentation/assets/guides/README.md` | Modify — G3, G4 entries + `.de.md` note |
| `core/src/localised_docs.py` | Create |
| `core/tests/test_localised_docs.py` | Create |
| `app.py` | Modify — help resolver, guide slug whitelist |
| `frontend/templates/modals/help_modal.html` | Modify — banner DOM |
| `frontend/templates/base.html` | Modify (section-help banner DOM) |
| `frontend/static/css/modals.css` | Modify — banner styling |
| `frontend/static/js/modules/modals.js` or `help.js` | Modify — banner show/hide logic |
| `frontend/static/i18n/en.json` | Modify — § 8 keys |
| `frontend/static/i18n/de.json` | Modify — § 8 keys |
| `frontend/tests/test_documentation_screenshots.py` | Modify — tests 93–99 |
| `frontend/tests/test_frontend.py` | Modify — 4 smoke tests |
| `documentation/UserManual.md`, `TechnicalManual.md` | Modify |

---

## 15. Post-Wave-5 — what's left out on purpose

Recorded here so future implementers don't redo the reasoning.

- **Per-paragraph fallback within a single help doc.** Not worth the parser complexity. Shipping a complete `help.de.md` is simpler.
- **DE screenshots for the four guides.** Doubles asset maintenance on every Spotify / OpenAI dashboard redesign. Text-only DE is the pragmatic stopping point.
- **Android APK voice input.** Scoped out in Wave 4 and stays out — requires permission-handling gymnastics specific to Chaquopy / Android WebView.
- **Native Anthropic / Gemini / Bedrock SDKs.** Out of scope; OpenAI-compatible protocol from Wave 4 covers the overwhelming majority of real requests.
- **Cost tracking over time.** Out of scope; requires a usage-log storage story that contradicts the privacy messaging from Wave 1.
- **Multi-playlist blending for profile seeding.** Wave 3's C.1 explicitly stopped at single-playlist seed. Revisit only if users ask.
- **Chart zoom / pan for the taste dashboard.** Overkill for 100-point scatter; hover tooltips are sufficient.

The design document ([`../design.md`](../design.md)) § "Deferred / open questions" remains the canonical list.

---

## 16. Opening contract for the implementer

You have full autonomy within Wave 5 scope. Do **not** implement anything outside it. When you believe Wave 5 is done, stop and say "Wave 5 complete — please review". After Wave 5 there is no planned Wave 6 — any follow-up work is driven by new user feedback, not the existing design document.
