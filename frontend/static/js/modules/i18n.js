export let _i18nStrings = {};

export async function switchLanguage(lang) {
    localStorage.setItem('svLang', lang);
    await applyLanguage(lang);
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

    const picker = document.getElementById('langPicker');
    if (picker) picker.value = lang;
}

export function i18n(key, fallback) {
    return _i18nStrings[key] !== undefined ? _i18nStrings[key] : (fallback || key);
}

export function initI18n() {
    const saved = localStorage.getItem('svLang') || 'en';
    setTimeout(() => applyLanguage(saved), 0);
    const picker = document.getElementById('langPicker');
    if (picker) picker.value = saved;
}
