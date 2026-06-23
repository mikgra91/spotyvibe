/**
 * quick_advanced.js — Generate-panel Quick / Advanced mode toggle.
 *
 * Quick mode: shared size slider + exploration slider + Generate button.
 * Advanced mode: all controls + presets + exploration + shared sliders.
 * Mode persists in localStorage.
 */

import { i18n } from './i18n.js';
import { el } from './dom.js';

const STORAGE_KEY = 'sv.gen_mode';
let _currentMode = 'quick';

function _getMode() {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved === 'quick' || saved === 'advanced') return saved;
    } catch (_) { /* ignore */ }
    return 'quick';
}

function _saveMode(mode) {
    try { localStorage.setItem(STORAGE_KEY, mode); } catch (_) { /* ignore */ }
}

function _applyMode(mode) {
    _currentMode = mode;

    // Toggle body visibility
    const quickBody = document.querySelector('.gen-mode-body--quick');
    const advBody = document.querySelector('.gen-mode-body--advanced');
    if (quickBody) quickBody.classList.toggle('hidden', mode !== 'quick');
    if (advBody)   advBody.classList.toggle('hidden', mode !== 'advanced');

    // Toggle button active states
    const tabs = document.querySelectorAll('.gen-mode-btn');
    tabs.forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-mode') === mode);
    });
}

function _updateSizeReadout(slider) {
    const row = slider.closest('.gen-size-row');
    if (!row) return;
    const readout = row.querySelector('.gen-size-value');
    if (readout) {
        readout.textContent = slider.value + ' ' + i18n('gen.size_suffix', 'tracks');
    }
    const min = parseFloat(slider.min) || 0;
    const max = parseFloat(slider.max) || 100;
    const val = parseFloat(slider.value) || 0;
    const pct = max > min ? ((val - min) / (max - min)) * 100 : 0;
    slider.style.setProperty('--fill-pct', pct + '%');
}

function _onTabClick(e) {
    const mode = e.currentTarget.getAttribute('data-mode');
    if (mode && mode !== _currentMode) {
        _saveMode(mode);
        _applyMode(mode);
    }
}


function _onSizeInput(e) {
    _updateSizeReadout(e.target);
}

function _onSizeBlur(e) {
    let val = parseInt(e.target.value, 10);
    if (isNaN(val) || val < 5) val = 5;
    if (val > 30) val = 30;
    // Snap to nearest step of 5
    val = Math.round(val / 5) * 5;
    e.target.value = val;
    _updateSizeReadout(e.target);
}

export function getMode() { return _currentMode; }

export function init() {
    _currentMode = _getMode();

    // Wire tab buttons
    document.querySelectorAll('.gen-mode-btn').forEach(btn => {
        btn.addEventListener('click', _onTabClick);
    });

    // Wire size slider (single shared instance)
    const sizeSlider = document.querySelector('.gen-size-slider');
    if (sizeSlider) {
        sizeSlider.addEventListener('input', _onSizeInput);
        sizeSlider.addEventListener('change', _onSizeBlur);
        _updateSizeReadout(sizeSlider);
    }

    // Also clamp the settings modal playlist-size on blur
    const settingsSize = el('settings-playlist-size');
    if (settingsSize) {
        settingsSize.addEventListener('blur', () => {
            let val = parseInt(settingsSize.value, 10);
            if (isNaN(val) || val < 5) val = 5;
            if (val > 30) val = 30;
            settingsSize.value = val;
        });
    }

    _applyMode(_currentMode);

    // Refresh readout when UI language changes
    document.addEventListener('sv:language-changed', () => {
        const s = document.querySelector('.gen-size-slider');
        if (s) _updateSizeReadout(s);
    });
}
