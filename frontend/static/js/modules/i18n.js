export let _i18nStrings = {};

export async function switchLanguage(lang) {
    localStorage.setItem('svLang', lang);
    await applyLanguage(lang);
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
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        if (_i18nStrings[key] !== undefined) el.placeholder = _i18nStrings[key];
    });
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const key = el.getAttribute('data-i18n-title');
        if (_i18nStrings[key] !== undefined) el.title = _i18nStrings[key];
    });

    _syncToggle(lang);
}

export function i18n(key, fallback) {
    return _i18nStrings[key] !== undefined ? _i18nStrings[key] : (fallback || key);
}

export function initI18n() {
    let saved = localStorage.getItem('svLang');
    if (!saved) {
        const browserLang = (navigator.language || '').split('-')[0].toLowerCase();
        saved = (browserLang === 'de') ? 'de' : 'en';
    }
    _syncToggle(saved);
    setTimeout(() => applyLanguage(saved), 0);
}
