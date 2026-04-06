import { showToast } from './ui.js';
import { i18n } from './i18n.js';

/* ── Human-readable hint descriptions ──────────────────────────────── */
const HINT_RANGES = {
    energy: [
        [0, 30, 'Calm, ambient'],
        [30, 60, 'Moderate'],
        [60, 80, 'Energetic'],
        [80, 100, 'Intense, aggressive'],
    ],
    valence: [
        [0, 30, 'Dark, melancholic'],
        [30, 60, 'Neutral, bittersweet'],
        [60, 80, 'Upbeat, positive'],
        [80, 100, 'Euphoric, joyful'],
    ],
    danceability: [
        [0, 30, 'Not danceable'],
        [30, 60, 'Moderate groove'],
        [60, 80, 'Danceable'],
        [80, 100, 'Club / dance-floor'],
    ],
    acousticness: [
        [0, 30, 'Electronic / electric'],
        [30, 60, 'Mixed'],
        [60, 80, 'Mostly acoustic'],
        [80, 100, 'Fully acoustic'],
    ],
    tempo: [
        [0, 80, 'Slow'],
        [80, 120, 'Moderate'],
        [120, 150, 'Up-tempo'],
        [150, 300, 'Fast'],
    ],
};

function describeValue(feature, val) {
    const ranges = HINT_RANGES[feature];
    if (!ranges) return '';
    for (const [lo, hi, label] of ranges) {
        if (val >= lo && val <= hi) return label;
    }
    return '';
}

export function updateFilterHint(feature) {
    const minEl = document.getElementById(`af-${feature}-min`);
    const maxEl = document.getElementById(`af-${feature}-max`);
    const hintEl = document.getElementById(`af-${feature}-hint`);
    if (!hintEl) return;

    const lo = minEl && minEl.value !== '' ? parseFloat(minEl.value) : null;
    const hi = maxEl && maxEl.value !== '' ? parseFloat(maxEl.value) : null;

    if (lo === null && hi === null) { hintEl.textContent = ''; return; }

    const loDesc = lo !== null ? describeValue(feature, lo) : '';
    const hiDesc = hi !== null ? describeValue(feature, hi) : '';

    if (loDesc && hiDesc && loDesc !== hiDesc) {
        hintEl.textContent = `↳ ${loDesc} to ${hiDesc}`;
    } else if (loDesc) {
        hintEl.textContent = `↳ ${loDesc}${hi === null ? '+' : ''}`;
    } else if (hiDesc) {
        hintEl.textContent = `↳ Up to ${hiDesc}`;
    } else {
        hintEl.textContent = '';
    }
}

export function updateAllFilterHints() {
    ['energy', 'valence', 'tempo', 'danceability', 'acousticness'].forEach(updateFilterHint);
}

export function toggleAudioFilters() {
    const body = document.getElementById('audioFiltersBody');
    const chevron = document.getElementById('audioFilterToggleBtn');
    const isHidden = body.classList.contains('hidden');
    body.classList.toggle('hidden', !isHidden);
    if (chevron) chevron.textContent = isHidden ? '▲' : '▼';
    const toggle = document.querySelector('#audioFiltersSection .audio-filter-toggle');
    if (toggle) toggle.setAttribute('aria-expanded', isHidden.toString());
    if (isHidden) updateAllFilterHints();
}

export function getAudioFilters() {
    const filters = {};
    const percentFeatures = new Set(['energy', 'valence', 'danceability', 'acousticness']);
    const features = ['energy','valence','tempo','danceability','acousticness'];
    features.forEach(f => {
        const minEl = document.getElementById(`af-${f}-min`);
        const maxEl = document.getElementById(`af-${f}-max`);
        let lo = minEl && minEl.value !== '' ? parseFloat(minEl.value) : null;
        let hi = maxEl && maxEl.value !== '' ? parseFloat(maxEl.value) : null;
        if (percentFeatures.has(f)) {
            if (lo !== null) lo = lo / 100;
            if (hi !== null) hi = hi / 100;
        }
        if (lo !== null || hi !== null) {
            filters[f] = {};
            if (lo !== null) filters[f].min = lo;
            if (hi !== null) filters[f].max = hi;
        }
    });
    return Object.keys(filters).length ? filters : null;
}

export function clearAllFilters() {
    const features = ['energy','valence','tempo','danceability','acousticness'];
    features.forEach(f => {
        const minEl = document.getElementById(`af-${f}-min`);
        const maxEl = document.getElementById(`af-${f}-max`);
        const hintEl = document.getElementById(`af-${f}-hint`);
        if (minEl) minEl.value = '';
        if (maxEl) maxEl.value = '';
        if (hintEl) hintEl.textContent = '';
    });
    showToast(i18n('af.all_cleared', 'All audio filters cleared.'), 'info');
}

/**
 * Apply a single analysis audio feature value as a filter range.
 * For 0–1 features: value ± 0.10, clamped to [0, 1].
 * For tempo: value ± 15 BPM, clamped to [0, 300].
 */
export function applyAnalysisFilter(feature, value) {
    const isTempo = feature === 'tempo';
    const isPercent = !isTempo;
    const displayValue = isPercent ? value * 100 : value;
    const offset = isTempo ? 15 : 10;
    const maxBound = isTempo ? 300 : 100;
    const step = isTempo ? 5 : 5;

    const lo = Math.max(0, displayValue - offset);
    const hi = Math.min(maxBound, displayValue + offset);

    const roundTo = (v, s) => Math.round(v / s) * s;
    const loRounded = roundTo(lo, step);
    const hiRounded = roundTo(hi, step);

    const minEl = document.getElementById(`af-${feature}-min`);
    const maxEl = document.getElementById(`af-${feature}-max`);
    if (minEl) minEl.value = loRounded;
    if (maxEl) maxEl.value = hiRounded;

    updateFilterHint(feature);

    // Ensure the filter panel is visible
    const body = document.getElementById('audioFiltersBody');
    if (body && body.classList.contains('hidden')) toggleAudioFilters();

    // Ensure Discover section is open
    const genBody = document.getElementById('generateBody');
    if (genBody && genBody.classList.contains('hidden')) {
        const genBtn = document.getElementById('generateToggleBtn');
        if (genBtn) genBtn.click();
    }

    const label = feature.charAt(0).toUpperCase() + feature.slice(1);
    const desc = isTempo ? `${loRounded}–${hiRounded} BPM` : `${loRounded}–${hiRounded}%`;
    showToast(i18n('af.filter_set', '{label} filter set to {range}').replace('{label}', label).replace('{range}', desc), 'success');
}

/**
 * Apply all audio features from an analysis result as filters at once.
 * @param {Object} audioFeatures - e.g. {energy: 0.72, valence: 0.58, tempo: 128, ...}
 */
export function applyAllAnalysisFilters(audioFeatures) {
    const supported = ['energy','valence','tempo','danceability','acousticness'];
    let count = 0;
    for (const f of supported) {
        if (audioFeatures[f] != null) {
            // Apply silently (no individual toasts)
            const isTempo = f === 'tempo';
            const isPercent = !isTempo;
            const displayValue = isPercent ? audioFeatures[f] * 100 : audioFeatures[f];
            const offset = isTempo ? 15 : 10;
            const maxBound = isTempo ? 300 : 100;
            const step = isTempo ? 5 : 5;
            const lo = Math.max(0, displayValue - offset);
            const hi = Math.min(maxBound, displayValue + offset);
            const roundTo = (v, s) => Math.round(v / s) * s;
            const loR = roundTo(lo, step);
            const hiR = roundTo(hi, step);
            const minEl = document.getElementById(`af-${f}-min`);
            const maxEl = document.getElementById(`af-${f}-max`);
            if (minEl) minEl.value = loR;
            if (maxEl) maxEl.value = hiR;
            updateFilterHint(f);
            count++;
        }
    }

    // Ensure panels are open
    const body = document.getElementById('audioFiltersBody');
    if (body && body.classList.contains('hidden')) toggleAudioFilters();
    const genBody = document.getElementById('generateBody');
    if (genBody && genBody.classList.contains('hidden')) {
        const genBtn = document.getElementById('generateToggleBtn');
        if (genBtn) genBtn.click();
    }

    showToast(i18n('af.filters_applied', '{count} audio filter(s) applied from analysis.').replace('{count}', count), 'success');
}
