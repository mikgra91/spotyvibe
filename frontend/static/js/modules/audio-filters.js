import { showToast } from './ui.js';
import { i18n } from './i18n.js';
import { el } from './dom.js';

/* ── Human-readable hint descriptions ──────────────────────────────── */
const HINT_RANGES = {
    energy: [
        [0, 15, 'Very calm, ambient'],
        [15, 30, 'Calm, mellow'],
        [30, 45, 'Laid-back'],
        [45, 60, 'Moderate'],
        [60, 75, 'Energetic'],
        [75, 90, 'High energy'],
        [90, 100, 'Intense, aggressive'],
    ],
    valence: [
        [0, 15, 'Very dark, bleak'],
        [15, 30, 'Dark, melancholic'],
        [30, 45, 'Bittersweet'],
        [45, 60, 'Neutral'],
        [60, 75, 'Upbeat, positive'],
        [75, 90, 'Joyful, bright'],
        [90, 100, 'Euphoric'],
    ],
    danceability: [
        [0, 20, 'Not danceable'],
        [20, 40, 'Slight groove'],
        [40, 60, 'Moderate groove'],
        [60, 75, 'Danceable'],
        [75, 90, 'Very danceable'],
        [90, 100, 'Club / dance-floor'],
    ],
    acousticness: [
        [0, 15, 'Fully electronic'],
        [15, 35, 'Mostly electronic'],
        [35, 55, 'Mixed'],
        [55, 75, 'Mostly acoustic'],
        [75, 90, 'Acoustic'],
        [90, 100, 'Fully acoustic'],
    ],
    tempo: [
        [0, 70, 'Very slow'],
        [70, 90, 'Slow'],
        [90, 110, 'Moderate'],
        [110, 130, 'Up-tempo'],
        [130, 160, 'Fast'],
        [160, 300, 'Very fast'],
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
    const minEl = el(`af-${feature}-min`);
    const maxEl = el(`af-${feature}-max`);
    const hintEl = el(`af-${feature}-hint`);
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
    const body = el('audioFiltersBody');
    const chevron = el('audioFilterToggleBtn');
    const isHidden = body.classList.contains('hidden');
    body.classList.toggle('hidden', !isHidden);
    if (chevron) chevron.textContent = isHidden ? '▲' : '▼';
    const toggle = document.querySelector('#audioFiltersSection .audio-filter-toggle');
    if (toggle) toggle.setAttribute('aria-expanded', isHidden.toString());
    if (isHidden) {
        updateAllFilterHints();
        // Wave 3: First filter open tip
        if (!localStorage.getItem('sv.filters_opened') && window.Tips) {
            localStorage.setItem('sv.filters_opened', '1');
            window.Tips.maybeTrigger('first_filter_open');
        }
    }
}

export function getAudioFilters() {
    const filters = {};
    const percentFeatures = new Set(['energy', 'valence', 'danceability', 'acousticness']);
    const features = ['energy','valence','tempo','danceability','acousticness'];
    features.forEach(f => {
        const minEl = el(`af-${f}-min`);
        const maxEl = el(`af-${f}-max`);
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
        const minEl = el(`af-${f}-min`);
        const maxEl = el(`af-${f}-max`);
        const hintEl = el(`af-${f}-hint`);
        if (minEl) minEl.value = '';
        if (maxEl) maxEl.value = '';
        if (hintEl) hintEl.textContent = '';
    });
    showToast(i18n('af.all_cleared', 'All audio filters cleared.'), 'info');
}

/* ── Adaptive offsets per feature ───────────────────────────────────── */
const FEATURE_OFFSETS = {
    energy:       8,   // ±8% — medium spread
    valence:      10,  // ±10% — wider, valence varies more
    danceability: 8,   // ±8%
    acousticness: 6,   // ±6% — narrow, values tend to cluster
    tempo:        12,  // ±12 BPM
};

/**
 * Apply a single analysis audio feature value as a filter range.
 * For 0–1 features: value ± 0.10, clamped to [0, 1].
 * For tempo: value ± 15 BPM, clamped to [0, 300].
 */
export function applyAnalysisFilter(feature, value) {
    const isTempo = feature === 'tempo';
    const isPercent = !isTempo;
    const displayValue = isPercent ? value * 100 : value;
    const offset = FEATURE_OFFSETS[feature] || (isTempo ? 12 : 8);
    const maxBound = isTempo ? 300 : 100;
    const step = isTempo ? 5 : 5;

    const lo = Math.max(0, displayValue - offset);
    const hi = Math.min(maxBound, displayValue + offset);

    const roundTo = (v, s) => Math.round(v / s) * s;
    const loRounded = roundTo(lo, step);
    const hiRounded = roundTo(hi, step);

    const minEl = el(`af-${feature}-min`);
    const maxEl = el(`af-${feature}-max`);
    if (minEl) minEl.value = loRounded;
    if (maxEl) maxEl.value = hiRounded;

    updateFilterHint(feature);

    // Ensure the filter panel is visible
    const body = el('audioFiltersBody');
    if (body && body.classList.contains('hidden')) toggleAudioFilters();

    // Ensure Discover section is open
    const genBody = el('generateBody');
    if (genBody && genBody.classList.contains('hidden')) {
        const genBtn = el('generateToggleBtn');
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
            const offset = FEATURE_OFFSETS[f] || (isTempo ? 12 : 8);
            const maxBound = isTempo ? 300 : 100;
            const step = isTempo ? 5 : 5;
            const lo = Math.max(0, displayValue - offset);
            const hi = Math.min(maxBound, displayValue + offset);
            const roundTo = (v, s) => Math.round(v / s) * s;
            const loR = roundTo(lo, step);
            const hiR = roundTo(hi, step);
            const minEl = el(`af-${f}-min`);
            const maxEl = el(`af-${f}-max`);
            if (minEl) minEl.value = loR;
            if (maxEl) maxEl.value = hiR;
            updateFilterHint(f);
            count++;
        }
    }

    // Ensure panels are open
    const body = el('audioFiltersBody');
    if (body && body.classList.contains('hidden')) toggleAudioFilters();
    const genBody = el('generateBody');
    if (genBody && genBody.classList.contains('hidden')) {
        const genBtn = el('generateToggleBtn');
        if (genBtn) genBtn.click();
    }

    showToast(i18n('af.filters_applied', '{count} audio filter(s) applied from analysis.').replace('{count}', count), 'success');
}
