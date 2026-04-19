import { el } from './dom.js';
import { loadHistory } from './history.js';
import * as State from './state.js';
/**
 * Tab-based section navigation.
 *
 * 3 tabs: openai, spotify, history
 * openai/spotify show their respective provider wrapper; history shows a standalone section.
 * Active tab is persisted in localStorage.
 */

const STORAGE_KEY = 'spotyvibe-active-tab';

const TABS = {
    openai:  { provider: 'openai' },
    spotify: { provider: 'spotify' },
    history: { provider: null },
};

// Migration map: old 5-tab names → new tab names
const _LEGACY_TAB_MAP = {
    profile:  'openai',
    analysis: 'openai',
    generate: 'spotify',
    review:   'spotify',
};

let _activeTab = 'openai';

export function initTabs() {
    // Restore last-active tab from localStorage (with legacy migration)
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            if (TABS[saved]) {
                _activeTab = saved;
            } else if (_LEGACY_TAB_MAP[saved]) {
                _activeTab = _LEGACY_TAB_MAP[saved];
                localStorage.setItem(STORAGE_KEY, _activeTab);
            }
        }
    } catch(e) {}

    // Wire up tab button clicks
    document.querySelectorAll('[data-tab]').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    // Keyboard navigation (arrow keys between tabs)
    const tabBar = document.querySelector('[role="tablist"]');
    if (tabBar) tabBar.addEventListener('keydown', _handleKeydown);

    // Apply initial tab state
    _applyTab(_activeTab);
}

export function switchTab(tabName) {
    if (!TABS[tabName]) return;
    _activeTab = tabName;
    _applyTab(tabName);
    try { localStorage.setItem(STORAGE_KEY, tabName); } catch(e) {}

}

export function getActiveTab() {
    return _activeTab;
}

/** Returns the provider ("openai" or "spotify") for the currently active tab, or "openai" as fallback. */
export function getActiveProvider() {
    return TABS[_activeTab]?.provider ?? 'openai';
}

function _applyTab(tabName) {
    // Update tab button states
    document.querySelectorAll('[data-tab]').forEach(btn => {
        const isActive = btn.dataset.tab === tabName;
        btn.setAttribute('aria-selected', isActive.toString());
        btn.classList.toggle('active', isActive);
        btn.setAttribute('tabindex', isActive ? '0' : '-1');
    });

    // Show/hide all tab panels
    const openaiEl = document.querySelector('.provider-openai');
    const spotifyEl = document.querySelector('.provider-spotify');
    const historyEl = el('historyPanel');
    if (openaiEl) openaiEl.classList.toggle('hidden', tabName !== 'openai');
    if (spotifyEl) spotifyEl.classList.toggle('hidden', tabName !== 'spotify');
    if (historyEl) historyEl.classList.toggle('hidden', tabName !== 'history');

    // Auto-load run history the first time the tab is shown. Without this,
    // the server-rendered "No runs yet." stays on screen until the user
    // manually toggles the Show button inside the section.
    if (tabName === 'history') {
        State.setHistoryBodyOpen(true);
        loadHistory();
    }
}

function _handleKeydown(e) {
    const tabs = [...document.querySelectorAll('[data-tab]')];
    const idx = tabs.findIndex(t => t === document.activeElement);
    if (idx === -1) return;

    if (e.key === 'ArrowRight') {
        e.preventDefault();
        const next = tabs[(idx + 1) % tabs.length];
        next.focus();
        switchTab(next.dataset.tab);
    } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        const prev = tabs[(idx - 1 + tabs.length) % tabs.length];
        prev.focus();
        switchTab(prev.dataset.tab);
    }
}
