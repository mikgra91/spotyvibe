import { showToast } from './ui.js';

/* ── Human-readable hint descriptions ──────────────────────────────── */
const HINT_RANGES = {
    energy: [
        [0, 0.3, 'Calm, ambient'],
        [0.3, 0.6, 'Moderate'],
        [0.6, 0.8, 'Energetic'],
        [0.8, 1.0, 'Intense, aggressive'],
    ],
    valence: [
        [0, 0.3, 'Dark, melancholic'],
        [0.3, 0.6, 'Neutral, bittersweet'],
        [0.6, 0.8, 'Upbeat, positive'],
        [0.8, 1.0, 'Euphoric, joyful'],
    ],
    danceability: [
        [0, 0.3, 'Not danceable'],
        [0.3, 0.6, 'Moderate groove'],
        [0.6, 0.8, 'Danceable'],
        [0.8, 1.0, 'Club / dance-floor'],
    ],
    acousticness: [
        [0, 0.3, 'Electronic / electric'],
        [0.3, 0.6, 'Mixed'],
        [0.6, 0.8, 'Mostly acoustic'],
        [0.8, 1.0, 'Fully acoustic'],
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
    if (isHidden) updateAllFilterHints();
}

export function getAudioFilters() {
    const filters = {};
    const features = ['energy','valence','tempo','danceability','acousticness'];
    features.forEach(f => {
        const minEl = document.getElementById(`af-${f}-min`);
        const maxEl = document.getElementById(`af-${f}-max`);
        const lo = minEl && minEl.value !== '' ? parseFloat(minEl.value) : null;
        const hi = maxEl && maxEl.value !== '' ? parseFloat(maxEl.value) : null;
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
    showToast('All audio filters cleared.', 'info');
}

/**
 * Apply a single analysis audio feature value as a filter range.
 * For 0–1 features: value ± 0.10, clamped to [0, 1].
 * For tempo: value ± 15 BPM, clamped to [0, 300].
 */
export function applyAnalysisFilter(feature, value) {
    const isTempo = feature === 'tempo';
    const offset = isTempo ? 15 : 0.10;
    const maxBound = isTempo ? 300 : 1;
    const step = isTempo ? 5 : 0.05;

    const lo = Math.max(0, value - offset);
    const hi = Math.min(maxBound, value + offset);

    // Round to step precision
    const roundTo = (v, s) => Math.round(v / s) * s;
    const loRounded = roundTo(lo, step);
    const hiRounded = roundTo(hi, step);

    const minEl = document.getElementById(`af-${feature}-min`);
    const maxEl = document.getElementById(`af-${feature}-max`);
    if (minEl) minEl.value = isTempo ? loRounded : loRounded.toFixed(2);
    if (maxEl) maxEl.value = isTempo ? hiRounded : hiRounded.toFixed(2);

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
    const desc = isTempo ? `${loRounded}–${hiRounded} BPM` : `${loRounded.toFixed(2)}–${hiRounded.toFixed(2)}`;
    showToast(`${label} filter set to ${desc}`, 'success');
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
            const offset = isTempo ? 15 : 0.10;
            const maxBound = isTempo ? 300 : 1;
            const step = isTempo ? 5 : 0.05;
            const lo = Math.max(0, audioFeatures[f] - offset);
            const hi = Math.min(maxBound, audioFeatures[f] + offset);
            const roundTo = (v, s) => Math.round(v / s) * s;
            const loR = roundTo(lo, step);
            const hiR = roundTo(hi, step);
            const minEl = document.getElementById(`af-${f}-min`);
            const maxEl = document.getElementById(`af-${f}-max`);
            if (minEl) minEl.value = isTempo ? loR : loR.toFixed(2);
            if (maxEl) maxEl.value = isTempo ? hiR : hiR.toFixed(2);
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

    showToast(`${count} audio filter(s) applied from analysis.`, 'success');
}
