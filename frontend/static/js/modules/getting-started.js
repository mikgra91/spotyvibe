/**
 * Getting Started — smart checklist (replaces the auto-tour).
 *
 * Fetches /api/onboarding/progress and renders a dismissable card with five
 * items that auto-check based on real app state. Hides itself when every
 * item is done or when the user has dismissed it.
 *
 * Replaces the role of the modal Quickstart for "what should I do next?"
 * guidance — see help-summary.md §6D.
 */
import { i18n } from './i18n.js';
import { el } from './dom.js';
import { openCredentials } from './modals.js';

const DISMISS_KEY = 'spotyvibe-getting-started-dismissed';

/* Each item declares its i18n key, a state-derived `done` predicate, and an
 * optional `jump` function that scrolls/expands the relevant section. */
function _items(state) {
    return [
        {
            key: 'getting_started.item_keys',
            fallback: 'Save your API keys',
            done: state.keys_saved,
            jump: () => openCredentials(),
        },
        {
            key: 'getting_started.item_spotify',
            fallback: 'Connect to Spotify',
            done: state.spotify_connected,
            jump: () => openCredentials(),
        },
        {
            key: 'getting_started.item_profile',
            fallback: 'Create a music profile',
            done: state.profile_created,
            jump: () => _expandSection('profile'),
        },
        {
            key: 'getting_started.item_playlist',
            fallback: 'Generate your first playlist',
            done: state.playlist_generated,
            jump: () => _expandSection('generate'),
        },
        {
            key: 'getting_started.item_feedback',
            fallback: 'Like or dislike at least 3 tracks',
            done: state.feedback_done,
            count: state.feedback_count,
            target: state.feedback_target,
            jump: () => _expandSection('review'),
        },
    ];
}

function _expandSection(slug) {
    // Map item slug → tab and optional accordion id
    const map = {
        profile:  { tab: 'openai',  accordion: 'trainSection' },
        generate: { tab: 'spotify', accordion: 'generateSection' },
        review:   { tab: 'spotify', accordion: 'reviewSection' },
    };
    const target = map[slug];
    if (!target) return;
    const tabBtn = document.getElementById(`tab-${target.tab}`);
    if (tabBtn) tabBtn.click();
    if (target.accordion) {
        const acc = document.getElementById(target.accordion);
        if (acc) {
            acc.scrollIntoView({ behavior: 'smooth', block: 'start' });
            const header = acc.querySelector('.section-header, [role="button"]');
            const isOpen = acc.classList.contains('open') || acc.getAttribute('aria-expanded') === 'true';
            if (!isOpen && header) header.click();
        }
    }
}

function _isDismissed() {
    try { return localStorage.getItem(DISMISS_KEY) === 'true'; } catch (_) { return false; }
}

function _setDismissed() {
    try { localStorage.setItem(DISMISS_KEY, 'true'); } catch (_) {}
}

function _render(state) {
    const card = el('gettingStartedCard');
    if (!card) return;

    if (_isDismissed()) { card.hidden = true; return; }

    const items = _items(state);
    const doneCount = items.filter(i => i.done).length;

    if (doneCount === items.length) { card.hidden = true; return; }

    const progress = el('gsProgress');
    if (progress) progress.textContent = `(${doneCount} / ${items.length})`;

    const list = el('gsList');
    if (list) {
        list.innerHTML = '';
        items.forEach((it, idx) => {
            const li = document.createElement('li');
            li.className = 'gs-item' + (it.done ? ' gs-done' : '');
            const mark = it.done ? '✓' : '○';
            const label = i18n(it.key, it.fallback);
            const detail = (!it.done && typeof it.count === 'number' && typeof it.target === 'number')
                ? ` <span class="gs-count">(${it.count} / ${it.target})</span>` : '';
            const jumpLabel = i18n('getting_started.jump', 'Jump');
            const jumpBtn = it.done
                ? ''
                : `<button type="button" class="gs-jump" data-gs-idx="${idx}">${jumpLabel} →</button>`;
            li.innerHTML = `<span class="gs-mark" aria-hidden="true">${mark}</span><span class="gs-label">${label}${detail}</span>${jumpBtn}`;
            list.appendChild(li);
        });
        list.querySelectorAll('.gs-jump').forEach(btn => {
            btn.addEventListener('click', () => {
                const idx = parseInt(btn.dataset.gsIdx, 10);
                const item = items[idx];
                if (item && typeof item.jump === 'function') item.jump();
            });
        });
    }

    card.hidden = false;
}

async function _fetchAndRender() {
    if (_isDismissed()) {
        const card = el('gettingStartedCard');
        if (card) card.hidden = true;
        return;
    }
    try {
        const res = await fetch('/api/onboarding/progress');
        if (!res.ok) return;
        const state = await res.json();
        _render(state);
    } catch (_) {
        // Silently swallow — card just stays hidden.
    }
}

export function initGettingStarted() {
    const card = el('gettingStartedCard');
    if (!card) return;
    const dismissBtn = el('gsDismiss');
    if (dismissBtn) {
        dismissBtn.addEventListener('click', () => {
            _setDismissed();
            card.hidden = true;
        });
    }
    _fetchAndRender();
}

/** Re-fetch progress (call after profile save, feedback, generation, etc). */
export function refreshGettingStarted() {
    _fetchAndRender();
}

// Expose for ad-hoc refreshes from inline onclicks/other modules
window.refreshGettingStarted = refreshGettingStarted;
