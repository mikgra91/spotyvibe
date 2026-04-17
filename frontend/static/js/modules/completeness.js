/**
 * completeness.js — Profile completeness score calculator & meter DOM updater.
 *
 * Computes a 0–100% "Profile Strength" based on five weighted dimensions:
 *   Core Description (40%), Must Have (25%), Soft Preferences (15%),
 *   Avoid (10%), User-edited (10%).
 *
 * The meter is visible only while score < 60%. Once ≥ 60 it flashes green
 * and hides.
 */

import { i18n } from './i18n.js';
import { el } from './dom.js';

// ── Mood/genre word set (case-insensitive substring match) ──────────
const MOOD_GENRE_WORDS = [
    'rock', 'pop', 'jazz', 'hiphop', 'hip-hop', 'rap', 'indie', 'electronic',
    'classical', 'metal', 'folk', 'country', 'ambient', 'techno', 'house',
    'soul', 'funk', 'blues', 'punk', 'upbeat', 'chill', 'energetic',
    'melancholic', 'happy', 'sad', 'dreamy', 'aggressive', 'calm',
    'theatrical', 'atmospheric', 'driving',
];

let _debounceTimer = null;
let _pristine = true; // tracks whether any field has been touched

// ── Dimension scorers ───────────────────────────────────────────────

function _scoreCore(text) {
    const len = (text || '').trim().length;
    if (len === 0) return { value: 0, state: 'empty', detail: '0 chars' };
    const lower = text.toLowerCase();
    const hasMood = MOOD_GENRE_WORDS.some(w => lower.includes(w));
    if (len >= 80 && hasMood) return { value: 1.0, state: 'strong', detail: `${len} chars` };
    return { value: 0.5, state: 'partial', detail: `${len} chars` };
}

function _scoreList(text, strongThreshold) {
    const lines = (text || '').split('\n').map(l => l.trim()).filter(Boolean);
    if (lines.length === 0) return { value: 0, state: 'empty', detail: '0 lines' };
    if (lines.length >= strongThreshold) return { value: 1.0, state: 'strong', detail: `${lines.length} lines` };
    return { value: 0.5, state: 'partial', detail: `${lines.length} line` };
}

function _scoreMustHave(text) { return _scoreList(text, 2); }
function _scoreSoftPrefs(text) {
    const lines = (text || '').split('\n').map(l => l.trim()).filter(Boolean);
    if (lines.length === 0) return { value: 0, state: 'empty', detail: '0 lines' };
    return { value: 1.0, state: 'strong', detail: `${lines.length} lines` };
}
function _scoreAvoid(text) {
    const lines = (text || '').split('\n').map(l => l.trim()).filter(Boolean);
    if (lines.length === 0) return { value: 0, state: 'empty', detail: '0 lines' };
    return { value: 1.0, state: 'strong', detail: `${lines.length} lines` };
}
function _scoreTouched() {
    if (!_pristine) return { value: 1.0, state: 'strong', detail: '✓' };
    return { value: 0, state: 'empty', detail: '—' };
}

// ── Score computation ───────────────────────────────────────────────

const DIMENSIONS = [
    { key: 'core',  weight: 0.40, label: 'profile.core_description', scorer: _scoreCore,     field: 'trainCoreDesc' },
    { key: 'must',  weight: 0.25, label: 'profile.must_have',        scorer: _scoreMustHave,  field: 'trainMustHave' },
    { key: 'soft',  weight: 0.15, label: 'profile.soft_preferences', scorer: _scoreSoftPrefs, field: 'trainSoftPrefs' },
    { key: 'avoid', weight: 0.10, label: 'profile.avoid',            scorer: _scoreAvoid,     field: 'trainAvoid' },
    { key: 'touch', weight: 0.10, label: 'profile.touched',          scorer: _scoreTouched,   field: null },
];

function compute() {
    let total = 0;
    const dims = [];
    for (const dim of DIMENSIONS) {
        let text = '';
        if (dim.field) {
            const el = el(dim.field);
            text = el ? el.value : '';
        }
        const result = dim.scorer(text);
        total += result.value * dim.weight;
        dims.push({ ...dim, ...result });
    }
    return { score: Math.round(total * 100), dims };
}

// ── Suggestion line ─────────────────────────────────────────────────

function _getSuggestion(dims) {
    const find = key => dims.find(d => d.key === key);
    const core = find('core');
    const must = find('must');
    const soft = find('soft');
    const avoid = find('avoid');

    if (core.state === 'empty')   return i18n('profile.suggest_core_empty', "Add a few sentences describing your ideal sound — that's the foundation.");
    if (must.state === 'empty')   return i18n('profile.suggest_must_empty', 'List 2–3 non-negotiable traits — things every suggestion must have.');
    if (soft.state === 'empty')   return i18n('profile.suggest_soft_empty', 'Add a soft preference for variety.');
    if (avoid.state === 'empty')  return i18n('profile.suggest_avoid_empty', 'Add at least one thing to avoid — it sharpens the profile.');
    if (core.state === 'partial') return i18n('profile.suggest_core_partial', 'Expand your core description — a sentence or two more helps GPT.');
    return '';
}

// ── DOM update ──────────────────────────────────────────────────────

const STATE_ICONS = { strong: '✓', partial: '◐', empty: '○' };

function _colorClass(score) {
    if (score < 30) return 'weak';
    if (score < 60) return 'ok';
    return 'strong';
}

function _render({ score, dims }) {
    const card = el('profileCompletenessCard');
    if (!card) return;

    const scoreEl = el('completenessScore');
    const fill = el('completenessBarFill');
    const tickList = el('completenessTicks');
    const suggestion = el('completenessSuggestion');

    const cls = _colorClass(score);

    // Score number
    if (scoreEl) {
        scoreEl.textContent = score + '%';
        scoreEl.className = 'completeness-score ' + cls;
    }

    // Bar
    if (fill) {
        fill.style.width = score + '%';
        fill.className = 'completeness-bar-fill ' + cls;
    }

    // Ticks
    if (tickList) {
        tickList.innerHTML = '';
        for (const dim of dims) {
            const li = document.createElement('li');
            li.className = 'completeness-tick ' + dim.state;
            li.innerHTML = `
                <span class="tick-icon">${STATE_ICONS[dim.state]}</span>
                <span class="tick-label" data-i18n="${dim.label}">${i18n(dim.label, dim.label)}</span>
                <span class="tick-value">${dim.detail}</span>
            `;
            tickList.appendChild(li);
        }
    }

    // Suggestion
    if (suggestion) {
        suggestion.textContent = _getSuggestion(dims);
    }

    // Visibility — always show while the profile editor is open
    if (score >= 60) {
        card.classList.add('is-complete');
    } else {
        card.classList.remove('is-complete');
    }
    card.classList.remove('hidden');
}

// ── Update (debounced) ──────────────────────────────────────────────

function _update() {
    const result = compute();
    _render(result);
}

function _scheduleUpdate() {
    _pristine = false;
    clearTimeout(_debounceTimer);
    _debounceTimer = setTimeout(_update, 250);
}

// ── Public API ──────────────────────────────────────────────────────

const DETAIL_STORAGE_KEY = 'sv.completeness_expanded';

export function toggleCompletenessDetail() {
    const detail = el('completenessDetail');
    const header = document.querySelector('.completeness-header');
    const chevron = el('completenessChevron');
    if (!detail) return;

    const isExpanding = detail.classList.contains('hidden');
    detail.classList.toggle('hidden', !isExpanding);
    if (header) header.setAttribute('aria-expanded', String(isExpanding));
    if (chevron) chevron.classList.toggle('rotated', isExpanding);

    try {
        localStorage.setItem(DETAIL_STORAGE_KEY, isExpanding ? '1' : '0');
    } catch (_) { /* ignore */ }
}

function _restoreDetailState() {
    try {
        const expanded = localStorage.getItem(DETAIL_STORAGE_KEY) === '1';
        const detail = el('completenessDetail');
        const header = document.querySelector('.completeness-header');
        const chevron = el('completenessChevron');
        if (expanded && detail) {
            detail.classList.remove('hidden');
            if (header) header.setAttribute('aria-expanded', 'true');
            if (chevron) chevron.classList.add('rotated');
        }
    } catch (_) { /* ignore */ }
}

export function init() {
    const fields = ['trainCoreDesc', 'trainMustHave', 'trainSoftPrefs', 'trainAvoid'];
    for (const id of fields) {
        const el = el(id);
        if (el) {
            el.addEventListener('input', _scheduleUpdate);
            el.addEventListener('change', _scheduleUpdate);
        }
    }

    // Also update after profile save/load via custom event
    document.addEventListener('profile-loaded', () => {
        _pristine = true;
        _update();
    });

    // Initial render (but only if the profile editor is open)
    const body = el('trainBody');
    if (body && !body.classList.contains('hidden')) {
        _update();
    }

    // Observe accordion open to trigger first render
    const observer = new MutationObserver(() => {
        if (body && !body.classList.contains('hidden')) {
            _update();
        }
    });
    if (body) {
        observer.observe(body, { attributes: true, attributeFilter: ['class'] });
    }

    // Restore collapsed/expanded state
    _restoreDetailState();

    // Expose toggle globally for onclick handlers
    window.toggleCompletenessDetail = toggleCompletenessDetail;
}

export { compute };

