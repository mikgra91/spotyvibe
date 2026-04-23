/**
 * rag_update_prompt.js — RAG corpus update tip notification
 *
 * Shows a non-blocking tip toast at the top of the page when a new RAG
 * corpus version is available (or none is installed yet). Reuses the
 * existing /api/settings response (`rag_update.status`) and
 * POST /api/rag/download-corpus endpoint.
 *
 * Behaviour:
 *  - Shows once per app load if status is 'update_available' or
 *    'missing_corpus'. A `sessionStorage` flag prevents repeat shows in
 *    the same tab session even if `init()` is called twice.
 *  - Dismiss just hides the tip — no further side effects.
 *  - "Download" POSTs the endpoint, shows progress, then closes on
 *    success and surfaces a toast.
 */
import { i18n } from './i18n.js';

const SHOWN_FLAG_KEY = 'sv.rag_update_prompt_shown';
const AUTO_DISMISS_MS = 20000;

let _tipElement = null;
let _autoDismissTimer = null;

function _dismiss() {
    if (_tipElement) {
        _tipElement.classList.add('hidden');
        setTimeout(() => { _tipElement?.remove(); _tipElement = null; }, 300);
    }
    if (_autoDismissTimer) {
        clearTimeout(_autoDismissTimer);
        _autoDismissTimer = null;
    }
}

function _showTip(status) {
    // Remove any existing tip
    const existing = document.getElementById('ragUpdateTip');
    if (existing) existing.remove();

    const isMissing = status === 'missing_corpus';
    const title = isMissing
        ? i18n('rag.update.title_first', 'Artist data available')
        : i18n('rag.update.title', 'New artist data available');
    const body = isMissing
        ? i18n('rag.update.body_first_time',
            'Download the offline MusicBrainz corpus to improve recommendations with real artist data.')
        : i18n('rag.update.body',
            'A newer version of the offline MusicBrainz corpus has been published. Download it now to improve recommendations?');

    const tip = document.createElement('div');
    tip.id = 'ragUpdateTip';
    tip.className = 'toast--tip rag-update-tip';
    tip.setAttribute('role', 'status');
    tip.setAttribute('aria-live', 'polite');
    tip.innerHTML = `
        <span class="toast-tip-icon">📦</span>
        <div class="toast-tip-text">
            <div class="toast-tip-title">${title}</div>
            <div class="toast-tip-body">${body}</div>
            <span class="rag-update-tip-status" id="ragUpdateTipStatus" hidden></span>
            <button class="toast-tip-link" id="ragUpdateTipDownload">${i18n('rag.update.download', 'Download')}</button>
        </div>
        <button class="toast-tip-close" aria-label="${i18n('tip.dismiss', 'Dismiss')}" id="ragUpdateTipClose">✕</button>
    `;
    document.body.appendChild(tip);
    _tipElement = tip;

    tip.querySelector('#ragUpdateTipDownload').addEventListener('click', _handleDownload);
    tip.querySelector('#ragUpdateTipClose').addEventListener('click', _dismiss);

    // Pause auto-dismiss on hover
    tip.addEventListener('mouseenter', () => {
        if (_autoDismissTimer) { clearTimeout(_autoDismissTimer); _autoDismissTimer = null; }
    });
    tip.addEventListener('mouseleave', () => {
        _autoDismissTimer = setTimeout(_dismiss, AUTO_DISMISS_MS);
    });

    _autoDismissTimer = setTimeout(_dismiss, AUTO_DISMISS_MS);

    try { sessionStorage.setItem(SHOWN_FLAG_KEY, '1'); } catch { /* ignore */ }
}

async function _handleDownload() {
    const dlBtn = _tipElement?.querySelector('#ragUpdateTipDownload');
    const statusLine = _tipElement?.querySelector('#ragUpdateTipStatus');
    if (dlBtn) dlBtn.disabled = true;
    if (statusLine) {
        statusLine.hidden = false;
        statusLine.textContent = i18n('rag.update.downloading', 'Downloading…');
    }
    // Cancel auto-dismiss during download
    if (_autoDismissTimer) { clearTimeout(_autoDismissTimer); _autoDismissTimer = null; }

    try {
        const resp = await fetch('/api/rag/download-corpus', { method: 'POST' });
        const body = await resp.json().catch(() => ({}));
        const { showToast } = await import('./ui.js');
        if (resp.ok) {
            showToast(i18n('rag.update.success', '✅ New artist data installed.'));
            _dismiss();
        } else {
            const detail = body.error || `HTTP ${resp.status}`;
            if (statusLine) {
                statusLine.textContent = i18n('rag.update.failed', 'Download failed: {detail}')
                    .replace('{detail}', detail);
            }
            if (dlBtn) dlBtn.disabled = false;
        }
    } catch (e) {
        if (statusLine) {
            statusLine.textContent = i18n('rag.update.failed', 'Download failed: {detail}')
                .replace('{detail}', e.message || 'network error');
        }
        if (dlBtn) dlBtn.disabled = false;
    }
}

export async function init() {
    // Skip if already shown in this tab session.
    try {
        if (sessionStorage.getItem(SHOWN_FLAG_KEY) === '1') return;
    } catch { /* ignore */ }

    try {
        const resp = await fetch('/api/settings');
        if (!resp.ok) return;
        const data = await resp.json();
        const status = data?.rag_update?.status;
        if (status === 'update_available' || status === 'missing_corpus') {
            _showTip(status);
        }
    } catch { /* offline / fetch failed → silent */ }
}
