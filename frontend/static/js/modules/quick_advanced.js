 /**
 * quick_advanced.js — Generate-panel Quick / Advanced mode toggle.
 *
 * Quick mode: size slider + exploration slider + Generate button.
 * Advanced mode: all controls + presets + exploration.
 * Mode persists in localStorage.
 */

import { i18n } from './i18n.js';

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

    // Sync size slider values between modes
    _syncSizeSliders();
}

function _syncSizeSliders() {
    const sliders = document.querySelectorAll('.gen-size-slider');
    if (sliders.length < 2) return;

    // Use the active mode's slider value as the source
    const activeBody = document.querySelector('.gen-mode-body:not(.hidden)');
    if (!activeBody) return;
    const activeSlider = activeBody.querySelector('.gen-size-slider');
    if (!activeSlider) return;

    const val = activeSlider.value;
    sliders.forEach(s => {
        if (s !== activeSlider) {
            s.value = val;
            _updateSizeReadout(s);
        }
    });
}

function _updateSizeReadout(slider) {
    const row = slider.closest('.gen-size-row');
    if (!row) return;
    const readout = row.querySelector('.gen-size-value');
    if (readout) {
        readout.textContent = slider.value + ' ' + i18n('gen.size_suffix', 'tracks');
    }
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
    // Keep all size sliders in sync
    const val = e.target.value;
    document.querySelectorAll('.gen-size-slider').forEach(s => {
        if (s !== e.target) {
            s.value = val;
            _updateSizeReadout(s);
        }
    });

    // Clamp value on blur
}

function _onSizeBlur(e) {
    let val = parseInt(e.target.value, 10);
    if (isNaN(val) || val < 10) val = 10;
    if (val > 30) val = 30;
    // Snap to nearest step of 5
    val = Math.round(val / 5) * 5;
    e.target.value = val;
    _updateSizeReadout(e.target);
    // Sync
    document.querySelectorAll('.gen-size-slider').forEach(s => {
        if (s !== e.target) {
            s.value = val;
            _updateSizeReadout(s);
        }
    });
}

export function getMode() { return _currentMode; }

export function init() {
    _currentMode = _getMode();

    // Wire tab buttons
    document.querySelectorAll('.gen-mode-btn').forEach(btn => {
        btn.addEventListener('click', _onTabClick);
    });

    // Wire size sliders
    document.querySelectorAll('.gen-size-slider').forEach(slider => {
        slider.addEventListener('input', _onSizeInput);
        slider.addEventListener('change', _onSizeBlur);
        _updateSizeReadout(slider);
    });

    // Also clamp the settings modal playlist-size on blur
    const settingsSize = document.getElementById('settings-playlist-size');
    if (settingsSize) {
        settingsSize.addEventListener('blur', () => {
            let val = parseInt(settingsSize.value, 10);
            if (isNaN(val) || val < 10) val = 10;
            if (val > 30) val = 30;
            settingsSize.value = val;
        });
    }

    _applyMode(_currentMode);
}

