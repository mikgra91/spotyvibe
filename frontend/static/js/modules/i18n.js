export let _i18nStrings = {};

export async function switchLanguage(lang) {
    localStorage.setItem('svLang', lang);
    await applyLanguage(lang);

    // Sync both GPT language and UI language to the server
    const langMap = { en: 'English', de: 'German', jp: 'Japanese' };
    const gptLang = langMap[lang];
    const payload = { ui_language: lang };
    if (gptLang) payload.gpt_language = gptLang;
    fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    }).catch(() => {}); // best-effort, don't block UI
}

function _syncToggle(lang) {
    document.querySelectorAll('.lang-toggle-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.lang === lang);
    });
}

export async function applyLanguage(lang) {
    try {
        const resp = await fetch(`/static/i18n/${lang}.json`);
        if (!resp.ok) return;
        _i18nStrings = await resp.json();
    } catch (e) { return; }

    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (_i18nStrings[key] !== undefined) el.textContent = _i18nStrings[key];
    });
    document.querySelectorAll('[data-i18n-html]').forEach(el => {
        const key = el.getAttribute('data-i18n-html');
        if (_i18nStrings[key] !== undefined) el.innerHTML = _i18nStrings[key];
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        if (_i18nStrings[key] !== undefined) el.placeholder = _i18nStrings[key];
    });
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const key = el.getAttribute('data-i18n-title');
        if (_i18nStrings[key] !== undefined) el.title = _i18nStrings[key];
    });
    document.querySelectorAll('[data-i18n-tooltip]').forEach(el => {
        const key = el.getAttribute('data-i18n-tooltip');
        if (_i18nStrings[key] !== undefined) el.setAttribute('data-tooltip', _i18nStrings[key]);
    });
    // data-i18n-attr="attr1:key1,attr2:key2" — generic per-attribute applier,
    // used for things like `aria-label` where a dedicated handler would be overkill.
    document.querySelectorAll('[data-i18n-attr]').forEach(el => {
        const spec = el.getAttribute('data-i18n-attr');
        if (!spec) return;
        spec.split(',').forEach(pair => {
            const [attr, key] = pair.split(':').map(s => s && s.trim());
            if (!attr || !key) return;
            if (_i18nStrings[key] !== undefined) el.setAttribute(attr, _i18nStrings[key]);
        });
    });

    _syncToggle(lang);

    // Notify dynamically-rendered components (presets, exploration, etc.)
    document.dispatchEvent(new CustomEvent('sv:language-changed', { detail: { lang } }));
}

export function i18n(key, fallback) {
    return _i18nStrings[key] !== undefined ? _i18nStrings[key] : (fallback || key);
}

/**
 * Localise an error payload returned by the backend.
 *
 * Accepts the parsed JSON body (or any object with `error_key` / `error`)
 * and returns a translated string, falling back to the English `error`
 * field. If `error_params` is present, `{name}` placeholders in the
 * translation are interpolated.
 */
export function localizedError(data, fallback) {
    if (!data || typeof data !== 'object') return fallback || '';
    const fallbackText = data.error || fallback || '';
    if (!data.error_key) return fallbackText;
    let text = i18n(data.error_key, fallbackText);
    const params = data.error_params;
    if (params && typeof params === 'object') {
        for (const k of Object.keys(params)) {
            text = text.replace('{' + k + '}', String(params[k]));
        }
    }
    return text;
}

window._localizedError = localizedError;

// Expose for non-module scripts (e.g. setup_guide.js)
window._i18n = i18n;

export async function initI18n() {
    // Fallback chain: server setting → localStorage → browser language
    let saved = null;
    try {
        const resp = await fetch('/api/settings');
        if (resp.ok) {
            const settings = await resp.json();
            if (settings.ui_language) saved = settings.ui_language;
        }
    } catch { /* ignore — use fallbacks */ }
    if (!saved) saved = localStorage.getItem('svLang');
    if (!saved) {
        const browserLang = (navigator.language || '').split('-')[0].toLowerCase();
        if (browserLang === 'de') saved = 'de';
        else if (browserLang === 'ja') saved = 'jp';
        else saved = 'en';
    }
    localStorage.setItem('svLang', saved);
    _syncToggle(saved);
    await applyLanguage(saved);
}
