import * as State from './state.js';
import { showStatus, showToast, showAlert, showConfirm, esc, sanitizeHtml } from './ui.js';
import { checkCredentialStatus, checkSpotifyAuth, fetchSettingsState } from './auth.js';
import { renderComponentWarnings } from './warnings.js';
import { renderProviderPills } from './provider-pills.js';
import { i18n } from './i18n.js';
import { quickstartReset } from './quickstart-tour.js';
import { initAllDemos, destroyAllDemos } from './quickstart-demo.js';
import { el } from './dom.js';

const CRED_KEYS = ['OPENAI_API_KEY', 'SPOTIPY_CLIENT_ID', 'SPOTIPY_CLIENT_SECRET'];

export async function clearCredential(key) {
    const ok = await showConfirm(i18n('cred.remove_confirm', 'Remove {key}?').replace('{key}', key));
    if (!ok) return;

    try {
        const resp = await fetch('/api/settings/credentials', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ [key]: '' }),
        });
        if (resp.ok) {
            const statusEl = el('status-' + key);
            statusEl.textContent = i18n('cred.status_not_set', '✗ Not set');
            statusEl.className = 'cred-status unset';
            el('clear-' + key).classList.add('hidden');
            el('cred-' + key).value = '';

            await Promise.all([checkCredentialStatus(), checkSpotifyAuth()]);
            renderComponentWarnings();

            showToast(i18n('cred.cleared', '{key} cleared.').replace('{key}', key), 'info');
        }
    } catch (e) {
        showAlert(i18n('msg.network_error', 'Network error: {detail}').replace('{detail}', e.message));
    }
}

export async function openCredentials() {
    el('settingsDropdown').classList.remove('open');

    CRED_KEYS.forEach(k => { el('cred-' + k).value = ''; });

    try {
        const resp = await fetch('/api/settings/credentials');
        const data = await resp.json();
        CRED_KEYS.forEach(k => {
            const statusEl = el('status-' + k);
            const clearBtn = el('clear-' + k);
            const info = data[k];
            if (info && info.is_set) {
                statusEl.textContent = i18n('cred.status_set', '✓ Set ({masked})').replace('{masked}', info.masked);
                statusEl.className = 'cred-status set';
                clearBtn.classList.remove('hidden');
            } else {
                statusEl.textContent = i18n('cred.status_not_set', '✗ Not set');
                statusEl.className = 'cred-status unset';
                clearBtn.classList.add('hidden');
            }
        });
    } catch (e) { /* ignore */ }

    el('credentialsModal').classList.add('open');
    _lastFocusedElement = _lastFocusedElement || document.activeElement;
    requestAnimationFrame(() => _focusFirstInModal(el('credentialsModal')));
}

export async function saveCredentials() {
    const payload = {};
    CRED_KEYS.forEach(k => {
        const val = el('cred-' + k).value.trim();
        if (val) payload[k] = val;
    });

    if (Object.keys(payload).length === 0) {
        closeModal('credentialsModal');
        return;
    }

    try {
        const resp = await fetch('/api/settings/credentials', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (resp.ok) {
            closeModal('credentialsModal');
            showStatus(i18n('cred.saved', '✅ Credentials saved.'), 'success');
            await Promise.all([checkCredentialStatus(), checkSpotifyAuth()]);
            renderComponentWarnings();
        } else {
            const d = await resp.json();
            showAlert(i18n('msg.error_prefix', 'Error: {detail}').replace('{detail}', d.error || 'unknown'));
        }
    } catch (e) {
        showAlert(i18n('msg.network_error', 'Network error: {detail}').replace('{detail}', e.message));
    }
}

export async function openSettings() {
    el('settingsDropdown').classList.remove('open');
    _lastFocusedElement = document.activeElement;
    el('settingsModal').classList.add('open');
    el('settingsLoading').classList.add('active');

    try {
        const resp = await fetch('/api/settings');
        const data = await resp.json();

        State.setDebugControlsAvailable(!!(data.debug_controls_available ?? true));
        const debugRow = el('debugModeRow');
        if (debugRow) debugRow.classList.toggle('hidden', !State.debugControlsAvailable);

        if (State.debugControlsAvailable) {
            const debugCheckbox = el('settings-debug');
            debugCheckbox.checked = !!data.debug_mode;
            const debugStatus = el('status-settings-debug');
            const debugLogPath = data.debug_log_path || 'debug.log';
            function updateDebugStatus() {
                const on = debugCheckbox.checked;
                debugStatus.textContent = on ? i18n('settings.debug_enabled', '✓ Enabled — log: {path}').replace('{path}', debugLogPath) : i18n('settings.debug_disabled', 'Disabled');
                debugStatus.className = 'cred-status ' + (on ? 'set' : 'unset');
            }
            updateDebugStatus();
            debugCheckbox.onchange = updateDebugStatus;
        }

        const ragCheckbox = el('settings-rag-enabled');
        if (ragCheckbox) {
            ragCheckbox.checked = !!data.rag_enabled;
            const ragStatus = el('status-settings-rag');
            let corpusAvailable = !!data.rag_corpus_available;

            // Replace the {count} placeholder in settings.rag.hint with the
            // actual server-side RAG_POOL_SIZE so the hint never drifts from
            // the constant in config.py.
            const ragHint = document.querySelector('[data-i18n="settings.rag.hint"]');
            if (ragHint && data.rag_pool_size != null) {
                ragHint.textContent = ragHint.textContent.replace('{count}', String(data.rag_pool_size));
            }
            function updateRagStatus() {
                if (!ragStatus) return;
                if (!corpusAvailable) {
                    ragStatus.textContent = i18n('settings.rag.missing', 'Corpus file not installed — toggle has no effect until artists.jsonl.gz is present.');
                    ragStatus.className = 'cred-status unset';
                } else if (ragCheckbox.checked) {
                    ragStatus.textContent = i18n('settings.rag.enabled', '✓ Candidate pool active');
                    ragStatus.className = 'cred-status set';
                } else {
                    ragStatus.textContent = i18n('settings.rag.disabled', 'Candidate pool disabled');
                    ragStatus.className = 'cred-status unset';
                }
            }
            updateRagStatus();
            ragCheckbox.onchange = updateRagStatus;
            if (!corpusAvailable) ragCheckbox.disabled = true;
            renderRagUpdateBanner(data.rag_update || { status: 'unknown' });
        }

        const modelStatus = el('status-settings-model');
        modelStatus.textContent = i18n('settings.model_status', '✓ Using: {model}').replace('{model}', data.model || 'gpt-5.4-mini');
        modelStatus.className = 'cred-status set';


    } catch (e) { /* ignore */ }

    const select = el('settings-model');
    select.innerHTML = `<option value="">${i18n('settings.loading_models', 'Loading models…')}</option>`;

    try {
        const resp = await fetch('/api/settings/models');
        const data = await resp.json();
        const models = data.models || [];
        const selected = data.selected || '';

        if (models.length > 0) {
            select.innerHTML = '';
            models.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m.id;
                opt.textContent = m.label;
                if (!m.supported) opt.style.color = 'var(--warning, #f0a030)';
                if (m.id === selected) opt.selected = true;
                select.appendChild(opt);
            });
        } else {
            select.innerHTML = '<option value="">' + (data.error ? i18n('settings.enter_key_first', 'Enter API key first') : i18n('settings.no_models', 'No models available')) + '</option>';
        }
    } catch (e) {
        select.innerHTML = `<option value="">${i18n('settings.models_load_failed', 'Could not load models')}</option>`;
    }

    el('settingsLoading').classList.remove('active');
}

export async function saveSettings() {
    const payload = {};

    const modelSelect = el('settings-model');
    if (modelSelect.value) {
        payload.model = modelSelect.value;
    }

    if (State.debugControlsAvailable) {
        payload.debug_mode = el('settings-debug').checked;
    }

    const ragCheckbox = el('settings-rag-enabled');
    if (ragCheckbox && !ragCheckbox.disabled) {
        payload.rag_enabled = ragCheckbox.checked;
    }



    try {
        const resp = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (resp.ok) {
            closeModal('settingsModal');
            showStatus(i18n('settings.saved', '✅ Settings saved.'), 'success');
            // Re-fetch settings (may change provider/llmApiKeyRequired),
            // then re-check credentials and update warnings
            fetchSettingsState().then(() =>
                checkCredentialStatus()
            ).then(() => {
                renderComponentWarnings();
                renderProviderPills();
            });
        } else {
            const d = await resp.json();
            showAlert(i18n('msg.error_prefix', 'Error: {detail}').replace('{detail}', d.error || 'unknown'));
        }
    } catch (e) {
        showAlert(i18n('msg.network_error', 'Network error: {detail}').replace('{detail}', e.message));
    }
}

export async function openHelp() {
    el('settingsDropdown').classList.remove('open');
    _lastFocusedElement = document.activeElement;
    _hideJumpBubble();
    _lockBodyScroll();
    el('helpModal').classList.add('open');

    if (State.helpLoaded) return;

    try {
        const resp = await fetch('/api/help');
        const data = await resp.json();
        if (data.html) {
            el('helpContent').innerHTML = sanitizeHtml(data.html);
            State.setHelpLoaded(true);

            // Wave 5: Show/hide fallback banner
            const banner = el('helpFallbackBanner');
            if (banner) banner.classList.toggle('hidden', !data.fallback_used);

            const helpContent = el('helpContent');
            helpContent.addEventListener('click', (e) => {
                const link = e.target.closest('a[href^="#"]');
                if (!link) return;
                e.preventDefault();
                const targetId = link.getAttribute('href').slice(1);
                const target = helpContent.querySelector('#' + CSS.escape(targetId));
                if (target) {
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            });
        } else {
            el('helpContent').innerHTML =
                '<p style="color:#e74c3c;">' + esc(i18n('help.load_failed', 'Could not load help content.')) + '</p>';
        }
    } catch (e) {
        el('helpContent').innerHTML =
            '<p style="color:#e74c3c;">' + esc(i18n('help.load_error', 'Failed to load help: {detail}').replace('{detail}', e.message)) + '</p>';
    }
}

export async function openSectionHelp(anchor) {
    const overlay = el('sectionHelpOverlay');
    const content = el('sectionHelpContent');
    content.innerHTML = `<p class="help-loading-text">${i18n('help.loading', 'Loading…')}</p>`;
    _hideJumpBubble();
    _lockBodyScroll();
    overlay.classList.add('open');

    try {
        const resp = await fetch('/api/help/section/' + encodeURIComponent(anchor));
        const data = await resp.json();
        if (data.html) {
            content.innerHTML = sanitizeHtml(data.html);
        } else {
            content.innerHTML =
                '<p style="color:#e74c3c;">' + esc(i18n('help.section_not_found', 'Section not found.')) + '</p>';
        }
    } catch (e) {
        content.innerHTML =
            '<p style="color:#e74c3c;">' + esc(i18n('help.load_error', 'Failed to load help: {detail}').replace('{detail}', e.message)) + '</p>';
    }
}

export function closeSectionHelp() {
    el('sectionHelpOverlay').classList.remove('open');
    _showJumpBubble();
    _unlockBodyScroll();
}

export async function openDataDir() {
    try {
        const resp = await fetch('/api/settings/open-data-dir', { method: 'POST' });
        const data = await resp.json();
        if (!resp.ok) {
            showToast(data.error || i18n('data_dir.open_failed', 'Could not open folder.'), 'error');
        }
    } catch (e) {
        showToast(i18n('msg.network_error', 'Network error: {detail}').replace('{detail}', e.message), 'error');
    }
}

/* ── Focus management for modals ── */
let _lastFocusedElement = null;

function _focusFirstInModal(modalEl) {
    const focusable = modalEl.querySelectorAll(
        'button:not([disabled]), [href], input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    if (focusable.length) focusable[0].focus();
}

function _trapFocus(e) {
    const openModal = document.querySelector('.modal-overlay.open')
        || document.querySelector('.spotify-preview-overlay.visible');
    if (!openModal) return;
    const focusable = openModal.querySelectorAll(
        'button:not([disabled]), [href], input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
    }
}

function _openModalWithFocus(id) {
    _lastFocusedElement = document.activeElement;
    const modal = el(id);
    modal.classList.add('open');
    requestAnimationFrame(() => _focusFirstInModal(modal));
}

export function closeModal(id) {
    el(id).classList.remove('open');
    if (id === 'helpModal') {
        _showJumpBubble();
        _unlockBodyScroll();
    }
    if (_lastFocusedElement && typeof _lastFocusedElement.focus === 'function') {
        _lastFocusedElement.focus();
        _lastFocusedElement = null;
    }
}

export function dismissHelpBanner() {
    const banner = el('helpFallbackBanner');
    if (banner) banner.classList.add('hidden');
}

export function dismissSectionHelpBanner() {
    const banner = el('sectionHelpFallbackBanner');
    if (banner) banner.classList.add('hidden');
}

/* ── Screenshot lightbox ── */

/** Minimum natural dimension (px) to show as expandable thumbnail. */
const LIGHTBOX_THRESHOLD = 300;

function _openScreenshotLightbox(imgEl) {
    const lb = el('screenshotLightbox');
    const lbImg = el('screenshotLightboxImg');
    if (!lb || !lbImg) return;
    lbImg.src = imgEl.src;
    lbImg.alt = imgEl.alt || 'Screenshot preview';
    lb.classList.add('open');
}

function _closeScreenshotLightbox() {
    const lb = el('screenshotLightbox');
    if (lb) lb.classList.remove('open');
}

/** Delegated click handler: expand help-content images in the lightbox. */
function _handleHelpImgClick(e) {
    const img = e.target.closest('img');
    if (!img) return;
    // If image is fully loaded, check natural dimensions; otherwise allow
    // expansion by default (images fetched via AJAX may not be decoded yet).
    const loaded = img.naturalWidth > 0 && img.naturalHeight > 0;
    if (loaded && img.naturalWidth <= LIGHTBOX_THRESHOLD && img.naturalHeight <= LIGHTBOX_THRESHOLD) {
        return; // small icon/badge — don't expand
    }
    e.preventDefault();
    e.stopPropagation();
    _openScreenshotLightbox(img);
}

// Attach delegated listeners once DOM is ready
function _initScreenshotLightbox() {
    // Delegate clicks on images inside help-content and section-help
    for (const id of ['helpContent', 'sectionHelpContent']) {
        const node = el(id);
        if (node) node.addEventListener('click', _handleHelpImgClick);
    }

    // Close lightbox via close button
    const closeBtn = el('screenshotLightboxClose');
    if (closeBtn) closeBtn.addEventListener('click', _closeScreenshotLightbox);

    // Close lightbox via click on backdrop or the image itself
    const lb = el('screenshotLightbox');
    if (lb) {
        lb.addEventListener('click', (e) => {
            // Close when clicking outside the image or on the image (zoom-out)
            if (e.target === lb || e.target.tagName === 'IMG') {
                _closeScreenshotLightbox();
            }
        });
    }
}

// Run once when module loads (DOM should be ready by then)
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initScreenshotLightbox);
} else {
    _initScreenshotLightbox();
}

/* ── Jump bubble visibility (no-op after tab navigation replaced the bubble) ── */
function _hideJumpBubble() {}
function _showJumpBubble() {}

/* ── Background scroll lock ── */
function _lockBodyScroll() {
    document.body.classList.add('modal-scroll-lock');
}
function _unlockBodyScroll() {
    // Only unlock if no overlay modals are still open
    const anyOpen = ['helpModal', 'quickstartModal', 'sectionHelpOverlay'].some(id => {
        const node = el(id);
        return node && node.classList.contains('open');
    });
    if (!anyOpen) document.body.classList.remove('modal-scroll-lock');
}

/* ── Quickstart guide modal ── */
const QUICKSTART_STORAGE_KEYS = {
    openai:  'spotyvibe-quickstart-openai-dismissed',
    spotify: 'spotyvibe-quickstart-spotify-dismissed',
};
// Legacy key — migrated to per-provider keys on first read
const QUICKSTART_STORAGE_KEY_LEGACY = 'spotyvibe-quickstart-dismissed';

// Tracks which provider's quickstart is currently open
let _quickstartProvider = 'openai';

/**
 * Open the quickstart guide.
 * @param {boolean} force — true when opened from the menu (always shows, doesn't reset dismiss flag)
 */
export function openQuickstart(force = false) {
    el('settingsDropdown').classList.remove('open');
    const provider = window.getActiveProvider?.() ?? 'openai';
    _quickstartProvider = provider;
    if (!force && _isQuickstartDismissed(provider)) return;
    _lastFocusedElement = document.activeElement;
    // Reflect the stored dismiss preference in the checkbox
    const wasDismissed = _isQuickstartDismissed(provider);
    document.querySelectorAll('.quickstartDontShowCb').forEach(cb => cb.checked = wasDismissed);
    // Reset to TOC page for this provider
    quickstartReset(provider);
    // Initialize demo players
    initAllDemos();
    _hideJumpBubble();
    _lockBodyScroll();
    el('quickstartModal').classList.add('open');
    requestAnimationFrame(() => _focusFirstInModal(el('quickstartModal')));
}

/**
 * Close the quickstart guide. Persists the "don't show again" preference
 * when any dismiss checkbox is checked.
 */
export function closeQuickstart() {
    const anyChecked = Array.from(document.querySelectorAll('.quickstartDontShowCb'))
        .some(cb => cb.checked);
    const key = QUICKSTART_STORAGE_KEYS[_quickstartProvider] ?? QUICKSTART_STORAGE_KEYS.openai;
    try {
        if (anyChecked) {
            localStorage.setItem(key, 'true');
        } else {
            localStorage.removeItem(key);
        }
    } catch (_) {}
    destroyAllDemos();
    closeModal('quickstartModal');
    _showJumpBubble();
    _unlockBodyScroll();
}

/**
 * Quickstart no longer auto-opens. Users invoke it from the menu (☰ → Quick Start).
 * Kept as an exported no-op for backward compatibility with callers and tests.
 */
export function maybeShowQuickstart(_provider = 'openai') {
    // intentionally empty — see help-summary.md §6A
}

function _isQuickstartDismissed(provider) {
    try {
        // One-time legacy migration: old single key → per-provider key
        const legacy = localStorage.getItem(QUICKSTART_STORAGE_KEY_LEGACY);
        if (legacy === 'true') {
            localStorage.setItem(QUICKSTART_STORAGE_KEYS.openai, 'true');
            localStorage.setItem(QUICKSTART_STORAGE_KEYS.spotify, 'true');
            localStorage.removeItem(QUICKSTART_STORAGE_KEY_LEGACY);
            return true;
        }
        const key = QUICKSTART_STORAGE_KEYS[provider] ?? QUICKSTART_STORAGE_KEYS.openai;
        return localStorage.getItem(key) === 'true';
    } catch (_) { return false; }
}

/* ── Close any open modal on Escape key + focus trap on Tab ── */
document.addEventListener('keydown', (e) => {
    if (e.key === 'Tab') {
        _trapFocus(e);
        return;
    }
    if (e.key !== 'Escape') return;
    // Close in priority order: lightbox → section help → quickstart → help modal → other modals
    const lightbox = el('screenshotLightbox');
    if (lightbox && lightbox.classList.contains('open')) {
        _closeScreenshotLightbox();
        return;
    }
    const sectionHelp = el('sectionHelpOverlay');
    if (sectionHelp && sectionHelp.classList.contains('open')) {
        closeSectionHelp();
        return;
    }
    const quickstart = el('quickstartModal');
    if (quickstart && quickstart.classList.contains('open')) {
        closeQuickstart();
        return;
    }
    for (const id of ['helpModal', 'credentialsModal', 'settingsModal']) {
        const node = el(id);
        if (node && node.classList.contains('open')) {
            closeModal(id);
            return;
        }
    }
});


function renderRagUpdateBanner(info) {
    const banner = el('settings-rag-update');
    const message = el('settings-rag-update-message');
    const button = el('settings-rag-update-btn');
    if (!banner || !message || !button) return;
    const status = info && info.status;
    const remoteVer = (info && info.remote && info.remote.corpus_version) || '';
    const localVer = (info && info.local_version) || '';
    if (status === 'missing_corpus') {
        message.textContent = i18n('settings.rag.banner.missing',
            'No corpus installed. Download the latest ({version}) to enable the candidate pool.')
            .replace('{version}', remoteVer);
        banner.hidden = false;
        button.disabled = false;
    } else if (status === 'update_available') {
        message.textContent = i18n('settings.rag.banner.update',
            'A newer corpus is available ({local} → {remote}).')
            .replace('{local}', localVer || '—')
            .replace('{remote}', remoteVer);
        banner.hidden = false;
        button.disabled = false;
    } else {
        banner.hidden = true;
    }
}

export async function downloadRagCorpus() {
    const button = el('settings-rag-update-btn');
    const message = el('settings-rag-update-message');
    if (button) button.disabled = true;
    if (message) message.textContent = i18n('settings.rag.banner.downloading', 'Downloading corpus…');
    try {
        const resp = await fetch('/api/rag/download-corpus', { method: 'POST' });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            const detail = data.detail || data.error || ('HTTP ' + resp.status);
            if (message) message.textContent = i18n('settings.rag.banner.failed',
                'Download failed: {error}').replace('{error}', detail);
            if (button) button.disabled = false;
            return;
        }
        if (typeof showToast === 'function') {
            showToast(i18n('settings.rag.banner.success',
                'Corpus installed ({version}).').replace('{version}', data.corpus_version || ''),
                'success');
        }
        const ragCheckbox = el('settings-rag-enabled');
        if (ragCheckbox) {
            ragCheckbox.disabled = false;
        }
        // Refresh the RAG status text to reflect newly available corpus
        const ragStatus = el('status-settings-rag');
        if (ragStatus) {
            ragStatus.textContent = ragCheckbox && ragCheckbox.checked
                ? i18n('settings.rag.enabled', '✓ Candidate pool active')
                : i18n('settings.rag.disabled', 'Candidate pool disabled');
            ragStatus.className = 'cred-status ' + (ragCheckbox && ragCheckbox.checked ? 'set' : 'unset');
        }
        const banner = el('settings-rag-update');
        if (banner) banner.hidden = true;
    } catch (e) {
        if (message) message.textContent = i18n('settings.rag.banner.failed',
            'Download failed: {error}').replace('{error}', String(e));
        if (button) button.disabled = false;
    }
}

