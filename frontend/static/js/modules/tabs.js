/**
 * Tab-based section navigation.
 * Replaces the scroll-aware jump bubble.
 *
 * 5 tabs: profile, generate, review, analysis, history
 * Each tab shows one section and its provider wrapper; hides all others.
 * Active tab is persisted in localStorage.
 */

const STORAGE_KEY = 'spotyvibe-active-tab';

const TABS = {
    profile:  { sectionId: 'trainSection',    provider: 'openai' },
    generate: { sectionId: 'generateSection', provider: 'spotify' },
    review:   { sectionId: 'reviewSection',   provider: 'spotify' },
    analysis: { sectionId: 'analysisSection', provider: 'openai' },
    history:  { sectionId: 'historySection',  provider: 'spotify' },
};

let _activeTab = 'profile';

export function initTabs() {
    // Restore last-active tab from localStorage
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved && TABS[saved]) _activeTab = saved;
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

function _applyTab(tabName) {
    const tabConfig = TABS[tabName];

    // Update tab button states
    document.querySelectorAll('[data-tab]').forEach(btn => {
        const isActive = btn.dataset.tab === tabName;
        btn.setAttribute('aria-selected', isActive.toString());
        btn.classList.toggle('active', isActive);
        btn.setAttribute('tabindex', isActive ? '0' : '-1');
    });

    // Show/hide individual sections
    Object.entries(TABS).forEach(([name, { sectionId }]) => {
        const el = document.getElementById(sectionId);
        if (el) el.classList.toggle('hidden', name !== tabName);
    });

    // Show/hide provider wrappers based on active provider
    const openaiEl = document.querySelector('.provider-openai');
    const spotifyEl = document.querySelector('.provider-spotify');
    if (openaiEl) openaiEl.classList.toggle('hidden', tabConfig.provider !== 'openai');
    if (spotifyEl) spotifyEl.classList.toggle('hidden', tabConfig.provider !== 'spotify');
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

