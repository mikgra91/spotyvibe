/**
 * Quickstart guide — pagination controller.
 *
 * Pages: 0 = Table of Contents, 1–6 = individual step pages.
 * The pagination bar (Back / dots / Next) is hidden on the TOC page
 * and shown on step pages. On the last step, Next becomes "Get Started".
 */
import { i18n } from './i18n.js';
import { qsDemoReset } from './quickstart-demo.js';

const TOTAL_PAGES = 7;   // 0 (TOC) + 6 steps
const LAST_STEP = 6;
let _currentPage = 0;

/* ── Public API ── */

/** Navigate to a specific page (0 = TOC, 1–6 = steps). */
export function quickstartGoTo(page) {
    if (page < 0 || page >= TOTAL_PAGES) return;
    _currentPage = page;
    _renderPage();
}

/** Go to the next page or close on the last step. */
export function quickstartNext() {
    if (_currentPage >= LAST_STEP) {
        // Last page → act like "Get Started"
        window.closeQuickstart();
        return;
    }
    quickstartGoTo(_currentPage + 1);
}

/** Go to the previous page. From page 1 → back to TOC. */
export function quickstartPrev() {
    quickstartGoTo(Math.max(0, _currentPage - 1));
}

/** Reset to the TOC page (called when the modal opens). */
export function quickstartReset() {
    _currentPage = 0;
    _renderPage();
}

/* ── Internal rendering ── */

function _renderPage() {
    const modal = document.querySelector('.quickstart-modal');
    if (!modal) return;

    // Show / hide pages
    modal.querySelectorAll('.qs-page').forEach(p => {
        const idx = parseInt(p.dataset.qsPage, 10);
        p.classList.toggle('qs-page-hidden', idx !== _currentPage);
        // Scroll the visible page to top
        if (idx === _currentPage) p.scrollTop = 0;
    });

    // Reset demo preview to frame 1 for the newly visible step page
    if (_currentPage >= 1) qsDemoReset(_currentPage);

    // Pagination bar — always visible (including TOC page)
    const pag = document.getElementById('qsPagination');
    if (pag) pag.classList.remove('qs-pag-hidden');

    // Dismiss row — always visible
    const dismissRow = document.getElementById('qsDismissRow');
    if (dismissRow) dismissRow.classList.remove('qs-pag-hidden');

    // Back/left button
    const prevBtn = document.getElementById('qsPagPrev');
    if (prevBtn) {
        prevBtn.classList.remove('qs-pag-invisible');
        const label = prevBtn.querySelector('[data-i18n="quickstart.prev"]');
        const arrow = prevBtn.querySelector('[aria-hidden="true"]');
        if (_currentPage === 0) {
            // TOC page: left button = "Get Started" (closes quickstart)
            if (label) label.textContent = i18n('quickstart.get_started', 'Get Started');
            if (arrow) arrow.textContent = '';
            prevBtn.onclick = () => window.closeQuickstart();
        } else {
            // Step pages: left button = "Contents" (page 1) or "Back"
            if (label) label.textContent = _currentPage <= 1
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
        if (_currentPage >= LAST_STEP) {
            if (label) label.textContent = i18n('quickstart.get_started', 'Get Started');
            if (arrow) arrow.textContent = '✓';
            nextBtn.classList.add('quickstart-go-btn');
        } else {
            if (label) label.textContent = i18n('quickstart.next', 'Next');
            if (arrow) arrow.textContent = '›';
            nextBtn.classList.remove('quickstart-go-btn');
        }
    }

    // Dot indicators
    _renderDots();
}

function _renderDots() {
    const container = document.getElementById('qsPagDots');
    if (!container) return;

    // Build dots: one for TOC (house icon) + 6 step dots
    let html = '';
    for (let i = 0; i < TOTAL_PAGES; i++) {
        const active = i === _currentPage ? ' qs-dot-active' : '';
        const label = i === 0 ? 'Contents' : `Step ${i}`;
        if (i === 0) {
            html += `<button class="qs-dot qs-dot-home${active}" onclick="quickstartGoTo(0)" aria-label="${label}" title="${label}">⌂</button>`;
        } else {
            html += `<button class="qs-dot${active}" onclick="quickstartGoTo(${i})" aria-label="${label}" title="${label}">${i}</button>`;
        }
    }
    container.innerHTML = html;
}

