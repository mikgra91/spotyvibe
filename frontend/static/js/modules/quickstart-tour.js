/**
 * Quickstart guide — pagination controller (provider-aware).
 *
 * Pages: 0 = Table of Contents (TOC), 1–6 = individual step pages.
 * Each step page carries a data-qs-provider attribute ("both", "openai", "spotify").
 * When opened, only the pages relevant to the active provider are shown.
 *
 * Navigation uses _visiblePageIndices — a filtered array of DOM page indices
 * that match the current provider. _posInVisible is the cursor into that array.
 */
import { i18n } from './i18n.js';
import { qsDemoReset, qsDemoAutoPlay } from './quickstart-demo.js';

let _currentProvider = 'openai';
let _visiblePageIndices = [0, 1, 2, 6]; // default: openai
let _posInVisible = 0;                   // index into _visiblePageIndices

/* ── Public API ── */

/**
 * Reset tour to TOC page for the given provider.
 * Recomputes the visible page set from data-qs-provider attributes.
 */
export function quickstartReset(provider = 'openai') {
    _currentProvider = provider;
    _computeVisiblePages(provider);
    _posInVisible = 0;
    _renderPage();
}

/** Navigate to a specific real page index (0–6). */
export function quickstartGoTo(realPageIdx) {
    const pos = _visiblePageIndices.indexOf(realPageIdx);
    if (pos === -1) return;   // page not visible for this provider
    _posInVisible = pos;
    _renderPage();
}

/** Go to the next page or close on the last step. */
export function quickstartNext() {
    if (_posInVisible >= _visiblePageIndices.length - 1) {
        window.closeQuickstart();
        return;
    }
    _posInVisible++;
    _renderPage();
}

/** Go to the previous page. */
export function quickstartPrev() {
    if (_posInVisible <= 0) return;
    _posInVisible--;
    _renderPage();
}

/* ── Internal ── */

function _computeVisiblePages(provider) {
    // Collect real page indices whose data-qs-provider matches provider or "both",
    // always include 0 (TOC).
    const pages = document.querySelectorAll('.qs-page[data-qs-page]');
    const result = [];
    pages.forEach(p => {
        const idx = parseInt(p.dataset.qsPage, 10);
        const prov = p.dataset.qsProvider;
        if (prov === 'toc' || prov === 'both' || prov === provider) {
            result.push(idx);
        }
    });
    result.sort((a, b) => a - b);
    _visiblePageIndices = result.length > 0 ? result : [0];
}

function _currentRealPageIdx() {
    return _visiblePageIndices[_posInVisible] ?? 0;
}

function _renderPage() {
    const modal = document.querySelector('.quickstart-modal');
    if (!modal) return;

    const realIdx = _currentRealPageIdx();

    // Update modal title for provider-specific branding
    const titleEl = document.getElementById('quickstartModalTitle');
    if (titleEl) {
        if (realIdx === 0) {
            // TOC page: show provider-specific title
            const titleKey = _currentProvider === 'openai'
                ? 'quickstart.title_openai'
                : 'quickstart.title_spotify';
            titleEl.textContent = i18n(titleKey, i18n('quickstart.title', '🚀 Quick Start Guide'));
        }
    }

    // Show / hide pages
    modal.querySelectorAll('.qs-page').forEach(p => {
        const idx = parseInt(p.dataset.qsPage, 10);
        p.classList.toggle('qs-page-hidden', idx !== realIdx);
        if (idx === realIdx) p.scrollTop = 0;
    });

    // On TOC page: hide irrelevant TOC entries
    if (realIdx === 0) {
        _renderToc();
    }

    // Reset demo preview for step pages and auto-play
    if (realIdx >= 1) {
        qsDemoReset(realIdx);
        qsDemoAutoPlay(realIdx);
    }

    // Pagination always visible
    const pag = document.getElementById('qsPagination');
    if (pag) pag.classList.remove('qs-pag-hidden');
    const dismissRow = document.getElementById('qsDismissRow');
    if (dismissRow) dismissRow.classList.remove('qs-pag-hidden');

    // Back/left button
    const prevBtn = document.getElementById('qsPagPrev');
    if (prevBtn) {
        prevBtn.classList.remove('qs-pag-invisible');
        const label = prevBtn.querySelector('[data-i18n="quickstart.prev"]');
        const arrow = prevBtn.querySelector('[aria-hidden="true"]');
        if (_posInVisible === 0) {
            // TOC: left button = "Get Started" (closes)
            if (label) label.textContent = i18n('quickstart.get_started', 'Get Started');
            if (arrow) arrow.textContent = '';
            prevBtn.onclick = () => window.closeQuickstart();
        } else {
            // Step: left = "Contents" (page 1) or "Back"
            if (label) label.textContent = _posInVisible <= 1
                ? i18n('quickstart.contents', 'Contents')
                : i18n('quickstart.prev', 'Back');
            if (arrow) arrow.textContent = '‹';
            prevBtn.onclick = () => quickstartPrev();
        }
    }

    // Next/right button
    const nextBtn = document.getElementById('qsPagNext');
    if (nextBtn) {
        const label = nextBtn.querySelector('[data-i18n="quickstart.next"]');
        const arrow = nextBtn.querySelector('[aria-hidden="true"]');
        const isLast = _posInVisible >= _visiblePageIndices.length - 1;
        if (isLast) {
            if (label) label.textContent = i18n('quickstart.get_started', 'Get Started');
            if (arrow) arrow.textContent = '✓';
            nextBtn.classList.add('quickstart-go-btn');
        } else {
            if (label) label.textContent = i18n('quickstart.next', 'Next');
            if (arrow) arrow.textContent = '›';
            nextBtn.classList.remove('quickstart-go-btn');
        }
    }

    _renderDots();
}

function _renderToc() {
    // Hide TOC entries whose provider doesn't match; keep "both"-tagged ones
    document.querySelectorAll('.qs-toc-entry[data-qs-provider]').forEach(btn => {
        const prov = btn.dataset.qsProvider;
        const visible = prov === 'both' || prov === _currentProvider;
        btn.classList.toggle('hidden', !visible);
    });
}

function _renderDots() {
    const container = document.getElementById('qsPagDots');
    if (!container) return;

    let html = '';
    _visiblePageIndices.forEach((realIdx, pos) => {
        const active = pos === _posInVisible ? ' qs-dot-active' : '';
        if (realIdx === 0) {
            html += `<button class="qs-dot qs-dot-home${active}" onclick="quickstartGoTo(0)" aria-label="Contents" title="Contents">⌂</button>`;
        } else {
            // Show sequential position number (1-based, excluding TOC)
            html += `<button class="qs-dot${active}" onclick="quickstartGoTo(${realIdx})" aria-label="Step ${pos}" title="Step ${pos}">${pos}</button>`;
        }
    });
    container.innerHTML = html;
}
