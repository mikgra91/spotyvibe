/**
 * tips.js — Feature discovery tip toasts (Wave 3 B.1)
 */
import { i18n } from './i18n.js';
import { el } from './dom.js';

const STORAGE_KEY = 'sv.tips.seen';
let sessionTipShown = false;

const TIP_CATALOGUE = {
    first_generation_complete: {
        id: 'first_generation_complete',
        title_i18n: 'tip.first_generation',
        body_i18n: 'tip.first_generation_body',
        link_i18n: 'tip.first_generation_link',
        linkAction: () => {
            const tab = el('tab-openai');
            if (tab) tab.click();
            const section = el('analysisSection');
            if (section) {
                section.scrollIntoView({ behavior: 'smooth' });
                const header = section.querySelector('.train-header');
                if (header) header.click();
            }
        },
    },
    disliked_2_plus: {
        id: 'disliked_2_plus',
        title_i18n: 'tip.disliked_2',
        body_i18n: 'tip.disliked_2_body',
        link_i18n: 'tip.disliked_2_link',
        linkAction: () => {
            const tab = el('tab-spotify');
            if (tab) tab.click();
            const section = el('reviewSection');
            if (section) {
                section.scrollIntoView({ behavior: 'smooth' });
                const header = section.querySelector('.train-header');
                if (header) header.click();
            }
        },
    },
    first_history_view: {
        id: 'first_history_view',
        title_i18n: 'tip.first_history',
        body_i18n: 'tip.first_history_body',
        link_i18n: 'tip.first_history_link',
        linkAction: () => {
            const trigger = el('profileMenuTrigger');
            if (trigger) trigger.click();
        },
    },
    first_filter_open: {
        id: 'first_filter_open',
        title_i18n: 'tip.first_filter',
        body_i18n: 'tip.first_filter_body',
        link_i18n: 'tip.first_filter_link',
        linkAction: () => { /* no sub-action */ },
    },
    first_refine_open: {
        id: 'first_refine_open',
        title_i18n: 'tip.first_refine',
        body_i18n: 'tip.first_refine_body',
        link_i18n: 'tip.first_refine_link',
        linkAction: () => {
            const picker = el('reviewPlaylistPicker');
            if (picker) picker.focus();
        },
    },
    first_analysis_open: {
        id: 'first_analysis_open',
        title_i18n: 'tip.first_analysis',
        body_i18n: 'tip.first_analysis_body',
        link_i18n: 'tip.first_analysis_link',
        linkAction: () => {
            const input = el('analysisArtist');
            if (input) input.focus();
        },
    },
    first_preview_open: {
        id: 'first_preview_open',
        title_i18n: 'preview.rate_hint',
        body_i18n: 'preview.rate_hint_body',
        link_i18n: 'tip.first_filter_link',
        linkAction: () => { /* no sub-action — just dismiss */ },
    },
    five_generations: {
        id: 'five_generations',
        title_i18n: 'tip.five_generations',
        body_i18n: 'tip.five_generations_body',
        link_i18n: 'tip.five_generations_link',
        linkAction: () => {
            const tab = el('tab-spotify');
            if (tab) tab.click();
            const section = el('generateSection');
            if (section) section.scrollIntoView({ behavior: 'smooth' });
        },
    },
};

function getSeenIds() {
    try {
        return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    } catch {
        return [];
    }
}

function markSeen(id) {
    const seen = getSeenIds();
    if (!seen.includes(id)) {
        seen.push(id);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(seen));
    }
}

let _autoDismissTimer = null;

function _dismissTip() {
    const toast = el('tipToast');
    if (toast) toast.classList.add('hidden');
    if (_autoDismissTimer) {
        clearTimeout(_autoDismissTimer);
        _autoDismissTimer = null;
    }
}

function _showTip(tip) {
    // Remove existing tip toast if any
    const existing = el('tipToast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.id = 'tipToast';
    toast.className = 'toast--tip';
    toast.setAttribute('role', 'status');
    toast.setAttribute('aria-live', 'polite');
    toast.innerHTML = `
        <span class="toast-tip-icon">💡</span>
        <div class="toast-tip-text">
            <div class="toast-tip-title">${i18n(tip.title_i18n, tip.id)}</div>
            <div class="toast-tip-body">${i18n(tip.body_i18n, '')}</div>
            <button class="toast-tip-link" id="tipToastLink">${i18n(tip.link_i18n, 'Open →')}</button>
        </div>
        <button class="toast-tip-close" aria-label="${i18n('tip.dismiss', 'Dismiss')}" id="tipToastClose">✕</button>
    `;
    document.body.appendChild(toast);

    toast.querySelector('#tipToastLink').addEventListener('click', () => {
        if (tip.linkAction) tip.linkAction();
        _dismissTip();
    });
    toast.querySelector('#tipToastClose').addEventListener('click', _dismissTip);

    // Pause auto-dismiss on hover
    toast.addEventListener('mouseenter', () => {
        if (_autoDismissTimer) { clearTimeout(_autoDismissTimer); _autoDismissTimer = null; }
    });
    toast.addEventListener('mouseleave', () => {
        _autoDismissTimer = setTimeout(_dismissTip, 12000);
    });

    _autoDismissTimer = setTimeout(_dismissTip, 12000);
}

/**
 * Try to show a tip by event id.
 * Only one tip per session; seen tips are skipped.
 */
export function maybeTrigger(id) {
    if (sessionTipShown) return;
    const tip = TIP_CATALOGUE[id];
    if (!tip) return;
    const seen = getSeenIds();
    if (seen.includes(id)) return;

    sessionTipShown = true;
    markSeen(id);
    _showTip(tip);
}

/**
 * Show a specific tip by id (for screenshot tests).
 */
export function showTipById(id) {
    const tip = TIP_CATALOGUE[id];
    if (!tip) return;
    _showTip(tip);
}

/**
 * Reset all seen tips.
 */
export function resetTipsSeen() {
    localStorage.removeItem(STORAGE_KEY);
    const { showToast } = window;
    if (showToast) {
        showToast(i18n('tip.reset_done', "Tips reset — you'll see them again as you use the app."));
    }
}

export function init() {
    // Make resetTipsSeen available globally for onclick
    window.resetTipsSeen = resetTipsSeen;
    window.Tips = { maybeTrigger, showTipById, resetTipsSeen };
}

