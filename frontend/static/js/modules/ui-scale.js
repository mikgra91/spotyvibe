const STORAGE_KEY = 'spv_ui_scale';
const VALID = ['0.9', '1', '1.1'];

function clean(v) {
    if (v === null || v === undefined) return '1';
    const s = String(v);
    return VALID.includes(s) ? s : '1';
}

export function setUiScale(value) {
    const v = clean(value);
    document.documentElement.style.setProperty('--ui-scale', v);
    try { localStorage.setItem(STORAGE_KEY, v); } catch (e) {}
    syncRadioGroup(v);
}

export function initUiScale() {
    let saved = '1';
    try { saved = clean(localStorage.getItem(STORAGE_KEY)); } catch (e) {}
    document.documentElement.style.setProperty('--ui-scale', saved);
    syncRadioGroup(saved);
}

function syncRadioGroup(value) {
    const radios = document.querySelectorAll('input[type="radio"][name="ui_scale"]');
    radios.forEach(r => { r.checked = (r.value === value); });
}
