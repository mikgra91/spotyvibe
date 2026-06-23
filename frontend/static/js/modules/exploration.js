/**
 * exploration.js — Exploration vs Accuracy slider.
 *
 * 5-notch composite slider. Each notch maps to:
 *   new_artist_pct, emerging_only, temperature.
 *
 * Two DOM instances (Quick + Advanced) kept in sync via one state owner.
 * Hand-editing underlying knobs in Advanced → "Custom" indicator.
 */

import { i18n } from './i18n.js';
import { el } from './dom.js';

// ── Notch definitions ───────────────────────────────────────────────

export const EXPLORATION_NOTCHES = {
    1: { label: 'gen.exploration_notch_1', hint: 'gen.exploration_hint_1', new_artist_pct: 10, emerging_only: false, temperature: 0.5 },
    2: { label: 'gen.exploration_notch_2', hint: 'gen.exploration_hint_2', new_artist_pct: 25, emerging_only: false, temperature: 0.7 },
    3: { label: 'gen.exploration_notch_3', hint: 'gen.exploration_hint_3', new_artist_pct: 50, emerging_only: false, temperature: 0.8 },
    4: { label: 'gen.exploration_notch_4', hint: 'gen.exploration_hint_4', new_artist_pct: 70, emerging_only: false, temperature: 0.9 },
    5: { label: 'gen.exploration_notch_5', hint: 'gen.exploration_hint_5', new_artist_pct: 90, emerging_only: true,  temperature: 1.0 },
};

let _currentNotch = 3;   // 1–5 or 'custom'
let _temperature = 0.8;  // in-memory, picked up at generation time

// ── Helpers ─────────────────────────────────────────────────────────

function _sliders() {
    return document.querySelectorAll('.exploration-slider');
}

function _fillWidth(val) {
    return ((val - 1) / 4) * 100;
}

function _updateSliderFill(slider) {
    const wrap = slider.closest('.exploration-slider-wrap');
    if (!wrap) return;
    let fill = wrap.querySelector('.exploration-slider-fill');
    if (!fill) {
        fill = document.createElement('div');
        fill.className = 'exploration-slider-fill';
        wrap.insertBefore(fill, wrap.firstChild);
    }
    fill.style.width = _fillWidth(parseInt(slider.value, 10)) + '%';
}

function _syncAllSliders(notch) {
    const numVal = typeof notch === 'number' ? notch : 3;
    for (const slider of _sliders()) {
        slider.value = numVal;
        _updateSliderFill(slider);

        if (notch === 'custom') {
            slider.classList.add('exploration-slider--custom');
        } else {
            slider.classList.remove('exploration-slider--custom');
        }
    }
}

function _updateLabels(notch) {
    const labels = document.querySelectorAll('.exploration-value');
    const hints = document.querySelectorAll('.exploration-row .inline-hint');

    if (notch === 'custom') {
        const labelText = i18n('gen.exploration_custom', 'Custom');
        const hintText = i18n('gen.exploration_hint_custom', 'Custom mix — move the slider to jump back to a preset.');
        labels.forEach(el => el.textContent = labelText);
        hints.forEach(el => el.textContent = hintText);
    } else {
        const def = EXPLORATION_NOTCHES[notch];
        if (!def) return;
        const labelText = i18n(def.label, def.label);
        const hintText = i18n(def.hint, def.hint);
        labels.forEach(el => el.textContent = labelText);
        hints.forEach(el => el.textContent = hintText);
    }
}

function _applyNotchToFields(notch) {
    if (notch === 'custom') return;
    const def = EXPLORATION_NOTCHES[notch];
    if (!def) return;

    // New artist %
    const napField = el('settings-new-artist-pct');
    if (napField) napField.value = def.new_artist_pct;

    const advNap = el('genNewArtistPct');
    if (advNap) advNap.value = def.new_artist_pct;

    // Emerging only
    const emergingCb = el('emergingArtistsCheckbox');
    if (emergingCb) emergingCb.checked = def.emerging_only;

    // Temperature (in-memory)
    _temperature = def.temperature;

    // Item 7 — applying a notch may change the New Artist % field; refresh
    // the "CUSTOM" badge so it disappears when the value matches the active
    // preset again.
    import('./presets.js').then(P => {
        if (typeof P.refreshNewArtistPctBadge === 'function') P.refreshNewArtistPctBadge();
    }).catch(() => { /* presets module not loaded — ignore */ });
}

// ── Custom detection ────────────────────────────────────────────────

function _detectCustom() {
    const napField = el('settings-new-artist-pct') ||
                     el('genNewArtistPct');
    const emergingCb = el('emergingArtistsCheckbox');

    const curNap = napField ? parseInt(napField.value, 10) : null;
    const curEmerging = emergingCb ? emergingCb.checked : false;

    for (const [n, def] of Object.entries(EXPLORATION_NOTCHES)) {
        if (def.new_artist_pct === curNap && def.emerging_only === curEmerging) {
            return parseInt(n, 10); // matches a notch
        }
    }
    return 'custom';
}

function onUnderlyingFieldChange() {
    const result = _detectCustom();
    _currentNotch = result;
    _syncAllSliders(result);
    _updateLabels(result);
    _saveState();
}

// ── Slider input handler ────────────────────────────────────────────

function _onSliderInput(e) {
    const notch = parseInt(e.target.value, 10);
    _currentNotch = notch;
    _syncAllSliders(notch);
    _updateLabels(notch);
    _applyNotchToFields(notch);
    _saveState();
}

// ── Persistence ─────────────────────────────────────────────────────

function _saveState() {
    try {
        localStorage.setItem('sv.exploration_notch', String(_currentNotch));
    } catch (_) { /* ignore */ }
}

function _loadState() {
    try {
        const saved = localStorage.getItem('sv.exploration_notch');
        if (saved === 'custom') return 'custom';
        const n = parseInt(saved, 10);
        if (n >= 1 && n <= 5) return n;
    } catch (_) { /* ignore */ }
    return 3; // default
}

// ── Public API ──────────────────────────────────────────────────────

export function getTemperature() {
    return _temperature;
}

export function getCurrentNotch() {
    return _currentNotch;
}

export function setNotch(notch) {
    _currentNotch = notch;
    _syncAllSliders(notch);
    _updateLabels(notch);
    if (notch !== 'custom') _applyNotchToFields(notch);
    _saveState();
}

export function init() {
    _currentNotch = _loadState();

    // Wire all slider instances
    for (const slider of _sliders()) {
        slider.addEventListener('input', _onSliderInput);
        _updateSliderFill(slider);
    }

    // Apply saved state
    _syncAllSliders(_currentNotch);
    _updateLabels(_currentNotch);
    if (_currentNotch !== 'custom') {
        _applyNotchToFields(_currentNotch);
    }

    // Listen to underlying field changes for custom detection
    const napField = el('settings-new-artist-pct');
    if (napField) {
        napField.addEventListener('input', onUnderlyingFieldChange);
        napField.addEventListener('change', onUnderlyingFieldChange);
    }
    const advNap = el('genNewArtistPct');
    if (advNap && advNap !== napField) {
        advNap.addEventListener('input', onUnderlyingFieldChange);
        advNap.addEventListener('change', onUnderlyingFieldChange);
    }
    const emergingCb = el('emergingArtistsCheckbox');
    if (emergingCb) {
        emergingCb.addEventListener('change', onUnderlyingFieldChange);
    }

    // Re-render labels when UI language changes
    document.addEventListener('sv:language-changed', () => {
        _updateLabels(_currentNotch);
    });
}




