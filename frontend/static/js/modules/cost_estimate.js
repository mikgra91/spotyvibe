/**
 * cost_estimate.js — Token & cost estimator widget (P0.1 rework)
 *
 * The Wave 4 estimator under-counted by ~10× because it ignored the deny set,
 * the full profile JSON, the RAG pool, and treated a 30-track playlist as one
 * call. The rework:
 *  - Multiplies tokens by ceil(tracks / batch_size).
 *  - Pulls the *real* prompt slice sizes from /api/profile/prompt-size so the
 *    estimate reflects what build_messages() actually sends.
 *  - Reports a separate "AI Profile Update" cost line.
 *  - Tracks cumulative session spend in localStorage.
 */
import { i18n } from './i18n.js';
import { el } from './dom.js';

let _pricingCache = null;
let _promptSizeCache = null;

const SESSION_SPEND_KEY = 'sv.cost.session_spend';

export function countTokens(text) {
    if (!text) return 0;
    return Math.ceil(text.length / 4);
}

export async function getPricing() {
    if (_pricingCache) return _pricingCache;
    try {
        const resp = await fetch('/static/data/pricing.json');
        _pricingCache = await resp.json();
    } catch (e) {
        _pricingCache = { models: {} };
    }
    return _pricingCache;
}

export async function getPromptSize({ force = false } = {}) {
    if (_promptSizeCache && !force) return _promptSizeCache;
    try {
        const resp = await fetch('/api/profile/prompt-size');
        if (!resp.ok) return null;
        const data = await resp.json();
        if (!data || !data.trained) return null;
        _promptSizeCache = data;
        return data;
    } catch (e) {
        return null;
    }
}

export function invalidatePromptSizeCache() {
    _promptSizeCache = null;
}

function _addSessionSpend(amount) {
    if (!amount || amount <= 0) return 0;
    let cur = 0;
    try { cur = parseFloat(localStorage.getItem(SESSION_SPEND_KEY) || '0') || 0; } catch (e) {}
    const next = cur + amount;
    try { localStorage.setItem(SESSION_SPEND_KEY, String(next)); } catch (e) {}
    return next;
}

function _getSessionSpend() {
    try { return parseFloat(localStorage.getItem(SESSION_SPEND_KEY) || '0') || 0; }
    catch (e) { return 0; }
}

export function recordRunSpend(amount) {
    const total = _addSessionSpend(amount);
    _refreshCumulative(total);
    return total;
}

export function resetSessionSpend() {
    try { localStorage.removeItem(SESSION_SPEND_KEY); } catch (e) {}
    _refreshCumulative(0);
}

export async function estimate({ model, profileText, tracks }) {
    const pricing = await getPricing();
    const prices = (pricing.models || {})[model];
    if (!prices) return null;

    const sizes = await getPromptSize();

    let profileTokens;
    let perBatchIn;
    let perBatchOut;
    let batchSize;

    if (sizes) {
        // Real prompt sizes from build_messages — accurate per-batch cost.
        batchSize = sizes.batch_size || 10;
        profileTokens = countTokens(' '.repeat(sizes.profile_chars || 0));
        // System + user message tokens, derived from the assembled prompt.
        perBatchIn = countTokens(' '.repeat((sizes.system_chars || 0) + (sizes.user_chars || 0)));
        // Output: each track produces ~150 tokens of JSON (artist, track,
        // rationale array, energy/valence, genres). +5 over-request buffer.
        perBatchOut = (batchSize + 5) * 150;
    } else {
        // Fallback: profile not trained / endpoint unavailable. Use the old
        // textarea-based heuristic so the widget still shows *something*.
        batchSize = 10;
        profileTokens = countTokens(profileText);
        perBatchIn = 600 + profileTokens + batchSize * 40;
        perBatchOut = batchSize * 80;
    }

    const batches = Math.max(1, Math.ceil(tracks / batchSize));
    const tokensIn = perBatchIn * batches;
    const tokensOut = perBatchOut * batches;
    const cost = (tokensIn / 1_000_000) * prices.input_per_1m
               + (tokensOut / 1_000_000) * prices.output_per_1m;

    // AI Profile Update: one call, sends profile + receives profile (~2× size)
    // plus a system prompt overhead. Approximated from the same endpoint.
    let aiUpdateCost = null;
    if (sizes && sizes.ai_update_chars) {
        const aiInTokens = countTokens(' '.repeat(sizes.ai_update_chars / 2 + 1500));
        const aiOutTokens = countTokens(' '.repeat(sizes.ai_update_chars / 2));
        aiUpdateCost = (aiInTokens / 1_000_000) * prices.input_per_1m
                     + (aiOutTokens / 1_000_000) * prices.output_per_1m;
    }

    return {
        model, profileTokens, tracks,
        batches, batchSize,
        tokensIn, tokensOut, cost,
        aiUpdateCost,
    };
}

function _getProfileText() {
    const fields = ['trainVibeDesc', 'trainCoreDesc', 'trainMustHave', 'trainSoftPrefs', 'trainAvoid'];
    return fields.map(id => {
        const node = el(id);
        return node ? node.value : '';
    }).join('\n');
}

function _getModel() {
    const freetext = el('settings-model-freetext');
    if (freetext && !freetext.classList.contains('hidden')) return freetext.value.trim();
    const select = el('settings-model');
    return select ? select.value : '';
}

function _getTracks() {
    // Read from shared size slider or settings
    const slider = document.querySelector('.gen-size-slider');
    if (slider) return parseInt(slider.value, 10) || 10;
    return parseInt(localStorage.getItem('sv.playlist_size') || '10', 10);
}

function _formatCost(cost) {
    if (cost < 0.01) return `$${cost.toFixed(4)}`;
    return `$${cost.toFixed(2)}`;
}

async function _refresh() {
    const model = _getModel();
    const profileText = _getProfileText();
    const tracks = _getTracks();

    const result = await estimate({ model, profileText, tracks });

    // Full card
    const card = el('costEstimateCard');
    const unavail = el('costUnavailable');

    if (card) {
        if (result) {
            if (el('costModelName')) el('costModelName').textContent = result.model;
            if (el('costProfileTokens')) el('costProfileTokens').textContent = i18n('cost.tokens_approx', '~{n} tokens').replace('{n}', result.profileTokens.toLocaleString());
            if (el('costTracks')) el('costTracks').textContent = i18n('cost.tracks_count', '{n} tracks').replace('{n}', result.tracks);
            if (el('costTokensIn')) el('costTokensIn').textContent = `~${result.tokensIn.toLocaleString()}`;
            if (el('costTokensOut')) el('costTokensOut').textContent = `~${result.tokensOut.toLocaleString()}`;
            if (el('costTotal')) el('costTotal').textContent = i18n('cost.cost_value', '≈ {amount}').replace('{amount}', _formatCost(result.cost));
            if (el('costBatches')) el('costBatches').textContent = `${result.batches} × ${result.batchSize}`;
            if (el('costAiUpdate')) {
                el('costAiUpdate').textContent = result.aiUpdateCost != null
                    ? i18n('cost.cost_value', '≈ {amount}').replace('{amount}', _formatCost(result.aiUpdateCost))
                    : '—';
            }
            if (unavail) unavail.classList.add('hidden');
        } else {
            if (unavail) unavail.classList.remove('hidden');
            if (el('costModelName')) el('costModelName').textContent = model || '—';
            if (el('costTotal')) el('costTotal').textContent = '—';
        }
    }

    _refreshCumulative(_getSessionSpend());

    // Footnote
    const footnote = el('costFootnote');
    const footnoteText = el('costFootnoteText');
    if (footnote && footnoteText) {
        if (result) {
            footnoteText.textContent = i18n('cost.footnote_tpl', '≈ {cost} · {model} · est.')
                .replace('{cost}', _formatCost(result.cost))
                .replace('{model}', result.model);
            footnote.classList.remove('hidden');
        } else {
            footnoteText.textContent = `— · ${model} · ${i18n('cost.footnote_unavailable', 'estimate unavailable')}`;
            footnote.classList.remove('hidden');
        }
    }

    // Popover card (inline under Generate button)
    _refreshPopoverCard(result, model);
}

function _refreshCumulative(total) {
    const node = el('costSessionTotal');
    if (!node) return;
    if (!total || total <= 0) {
        node.textContent = i18n('cost.session_zero', '$0.00');
    } else {
        node.textContent = _formatCost(total);
    }
}

function _refreshPopoverCard(result, model) {
    const unavail = el('costPopUnavailable');

    if (result) {
        if (el('costPopModelName')) el('costPopModelName').textContent = result.model;
        if (el('costPopProfileTokens')) el('costPopProfileTokens').textContent = i18n('cost.tokens_approx', '~{n} tokens').replace('{n}', result.profileTokens.toLocaleString());
        if (el('costPopTracks')) el('costPopTracks').textContent = i18n('cost.tracks_count', '{n} tracks').replace('{n}', result.tracks);
        if (el('costPopTokensIn')) el('costPopTokensIn').textContent = `~${result.tokensIn.toLocaleString()}`;
        if (el('costPopTokensOut')) el('costPopTokensOut').textContent = `~${result.tokensOut.toLocaleString()}`;
        if (el('costPopTotal')) el('costPopTotal').textContent = i18n('cost.cost_value', '≈ {amount}').replace('{amount}', _formatCost(result.cost));
        if (unavail) unavail.classList.add('hidden');
    } else {
        if (el('costPopModelName')) el('costPopModelName').textContent = model || '—';
        if (el('costPopTotal')) el('costPopTotal').textContent = '—';
        if (unavail) unavail.classList.remove('hidden');
    }
}

export function toggleCostPopover(e) {
    if (e) e.stopPropagation();
    const popover = el('costPopoverCard');
    const footnote = el('costFootnote');
    if (!popover) return;

    const isOpen = !popover.classList.contains('hidden');
    popover.classList.toggle('hidden', isOpen);
    if (footnote) footnote.setAttribute('aria-expanded', String(!isOpen));
}

function _closeCostPopover() {
    const popover = el('costPopoverCard');
    const footnote = el('costFootnote');
    if (popover) popover.classList.add('hidden');
    if (footnote) footnote.setAttribute('aria-expanded', 'false');
}

let _debounceTimer = null;
function _debouncedRefresh() {
    clearTimeout(_debounceTimer);
    _debounceTimer = setTimeout(_refresh, 200);
}

export function init() {
    // Preload pricing
    getPricing();

    // Wire listeners for live refresh
    ['trainVibeDesc', 'trainCoreDesc', 'trainMustHave', 'trainSoftPrefs', 'trainAvoid'].forEach(id => {
        const node = el(id);
        if (node) node.addEventListener('blur', _debouncedRefresh);
    });

    const modelSelect = el('settings-model');
    if (modelSelect) modelSelect.addEventListener('change', _debouncedRefresh);

    const modelFreetext = el('settings-model-freetext');
    if (modelFreetext) modelFreetext.addEventListener('input', _debouncedRefresh);

    // Size slider → refresh cost estimate
    const sizeSlider = el('genSize');
    if (sizeSlider) sizeSlider.addEventListener('input', _debouncedRefresh);

    // Settings modal open → invalidate prompt-size cache (profile may have
    // changed since last open) and refresh.
    const settingsModal = el('settingsModal');
    if (settingsModal) {
        const observer = new MutationObserver(() => {
            if (settingsModal.classList.contains('open')) {
                invalidatePromptSizeCache();
                _refresh();
            }
            // Disconnect if modal is removed from DOM
            if (!document.body.contains(settingsModal)) observer.disconnect();
        });
        observer.observe(settingsModal, { attributes: true, attributeFilter: ['class'] });
    }

    // Initial refresh after a short delay
    setTimeout(_refresh, 500);

    // Expose popover toggle globally for onclick handlers
    window.toggleCostPopover = toggleCostPopover;

    // Dismiss popover on click-outside
    document.addEventListener('click', (e) => {
        const popover = el('costPopoverCard');
        const footnote = el('costFootnote');
        if (popover && !popover.classList.contains('hidden')) {
            if (!popover.contains(e.target) && !footnote?.contains(e.target)) {
                _closeCostPopover();
            }
        }
    });

    // Dismiss popover on Escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') _closeCostPopover();
    });
}

