/**
 * rag_update_prompt.js — Item C (2026-04)
 *
 * Shows a small startup popup when a new RAG corpus version is available
 * (or none is installed yet). Reuses the existing /api/settings response
 * (`rag_update.status`) and POST /api/rag/download-corpus endpoint.
 *
 * Behaviour:
 *  - Shows once per app load if status is 'update_available' or
 *    'missing_corpus'. A `sessionStorage` flag prevents repeat shows in
 *    the same tab session even if `init()` is called twice.
 *  - Cancel just dismisses the modal — no further side effects.
 *  - Download POSTs the endpoint, shows a status line, then closes on
 *    success and surfaces a toast.
 */
import { i18n } from './i18n.js';
import { el } from './dom.js';

const SHOWN_FLAG_KEY = 'sv.rag_update_prompt_shown';

let _wired = false;

function _showModal(status) {
    const modal = el('ragUpdateModal');
    if (!modal) return;
    const body = el('ragUpdateBody');
    if (body) {
        const key = status === 'missing_corpus'
            ? 'rag.update.body_first_time'
            : 'rag.update.body';
        body.textContent = i18n(key, body.textContent || '');
    }
    const statusLine = el('ragUpdateStatus');
    if (statusLine) {
        statusLine.hidden = true;
        statusLine.textContent = '';
    }
    const dlBtn = el('ragUpdateDownloadBtn');
    const cancelBtn = el('ragUpdateCancelBtn');
    if (dlBtn) dlBtn.disabled = false;
    if (cancelBtn) cancelBtn.disabled = false;

    modal.hidden = false;
    modal.classList.add('open');
    try { sessionStorage.setItem(SHOWN_FLAG_KEY, '1'); } catch { /* ignore */ }
}

function _closeModal() {
    const modal = el('ragUpdateModal');
    if (!modal) return;
    modal.classList.remove('open');
    modal.hidden = true;
}

async function _handleDownload() {
    const dlBtn = el('ragUpdateDownloadBtn');
    const cancelBtn = el('ragUpdateCancelBtn');
    const statusLine = el('ragUpdateStatus');
    if (dlBtn) dlBtn.disabled = true;
    if (cancelBtn) cancelBtn.disabled = true;
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
            _closeModal();
        } else {
            const detail = body.error || `HTTP ${resp.status}`;
            if (statusLine) {
                statusLine.textContent = i18n('rag.update.failed', 'Download failed: {detail}')
                    .replace('{detail}', detail);
            }
            if (dlBtn) dlBtn.disabled = false;
            if (cancelBtn) cancelBtn.disabled = false;
        }
    } catch (e) {
        if (statusLine) {
            statusLine.textContent = i18n('rag.update.failed', 'Download failed: {detail}')
                .replace('{detail}', e.message || 'network error');
        }
        if (dlBtn) dlBtn.disabled = false;
        if (cancelBtn) cancelBtn.disabled = false;
    }
}

function _wire() {
    if (_wired) return;
    _wired = true;
    el('ragUpdateCancelBtn')?.addEventListener('click', _closeModal);
    el('ragUpdateDownloadBtn')?.addEventListener('click', _handleDownload);
}

export async function init() {
    _wire();

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
            _showModal(status);
        }
    } catch { /* offline / fetch failed → silent */ }
}

