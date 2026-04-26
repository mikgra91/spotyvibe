/**
 * rag_update_prompt.js — Artist-data update tip notification
 *
 * Shows a non-blocking tip at the top of the page when a new artist
 * database version is available (or none is installed yet). Reuses the
 * existing /api/settings response (`rag_update.status`) and
 * POST /api/rag/download-corpus endpoint.
 *
 * Behaviour:
 *  - Shows on every app start when status is 'update_available' or
 *    'missing_corpus'. There is no per-session suppression: the user
 *    explicitly asked for a re-show on every launch (the tip is the
 *    only place outside ⚙️ Settings where the download is offered).
 *  - The tip stays on screen until the user dismisses it or clicks
 *    Download. There is no auto-dismiss timer.
 *  - "Download" POSTs the endpoint, shows progress, then closes on
 *    success and surfaces a toast.
 */
import { i18n } from './i18n.js';

let _tipElement = null;

function _dismiss() {
    if (_tipElement) {
        _tipElement.classList.add('hidden');
        setTimeout(() => { _tipElement?.remove(); _tipElement = null; }, 300);
    }
}

function _showTip(status) {
    // Remove any existing tip
    const existing = document.getElementById('ragUpdateTip');
    if (existing) existing.remove();

    const isMissing = status === 'missing_corpus';
    const title = isMissing
        ? i18n('rag.update.title_first', 'Artist database available')
        : i18n('rag.update.title', 'New artist database available');
    const body = isMissing
        ? i18n('rag.update.body_first_time',
            'An offline artist database is available to improve recommendations. Download it now.')
        : i18n('rag.update.body',
            'A newer version of the offline artist database has been published. Download it for better recommendations.');

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
}

async function _handleDownload() {
    const dlBtn = _tipElement?.querySelector('#ragUpdateTipDownload');
    const statusLine = _tipElement?.querySelector('#ragUpdateTipStatus');
    if (dlBtn) dlBtn.disabled = true;
    if (statusLine) {
        statusLine.hidden = false;
        statusLine.textContent = i18n('rag.update.downloading', 'Downloading…');
    }

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
