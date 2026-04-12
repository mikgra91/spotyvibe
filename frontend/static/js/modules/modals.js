import * as State from './state.js';
import { showStatus, showToast, showAlert, showConfirm, esc, sanitizeHtml } from './ui.js';
import { checkCredentialStatus, checkSpotifyAuth, fetchSettingsState } from './auth.js';
import { renderComponentWarnings } from './warnings.js';
import { renderProviderPills } from './provider-pills.js';
import { i18n } from './i18n.js';
import { quickstartReset } from './quickstart-tour.js';
import { initAllDemos, destroyAllDemos } from './quickstart-demo.js';

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
            const el = document.getElementById('status-' + key);
            el.textContent = i18n('cred.status_not_set', '✗ Not set');
            el.className = 'cred-status unset';
            document.getElementById('clear-' + key).classList.add('hidden');
            document.getElementById('cred-' + key).value = '';

            await Promise.all([checkCredentialStatus(), checkSpotifyAuth()]);
            renderComponentWarnings();

            showToast(i18n('cred.cleared', '{key} cleared.').replace('{key}', key), 'info');
        }
    } catch (e) {
        showAlert(i18n('msg.network_error', 'Network error: {detail}').replace('{detail}', e.message));
    }
}

export async function openCredentials() {
    document.getElementById('settingsDropdown').classList.remove('open');

    CRED_KEYS.forEach(k => { document.getElementById('cred-' + k).value = ''; });

    try {
        const resp = await fetch('/api/settings/credentials');
        const data = await resp.json();
        CRED_KEYS.forEach(k => {
            const el = document.getElementById('status-' + k);
            const clearBtn = document.getElementById('clear-' + k);
            const info = data[k];
            if (info && info.is_set) {
                el.textContent = i18n('cred.status_set', '✓ Set ({masked})').replace('{masked}', info.masked);
                el.className = 'cred-status set';
                clearBtn.classList.remove('hidden');
            } else {
                el.textContent = i18n('cred.status_not_set', '✗ Not set');
                el.className = 'cred-status unset';
                clearBtn.classList.add('hidden');
            }
        });
    } catch (e) { /* ignore */ }

    document.getElementById('credentialsModal').classList.add('open');
    _lastFocusedElement = _lastFocusedElement || document.activeElement;
    requestAnimationFrame(() => _focusFirstInModal(document.getElementById('credentialsModal')));
}

export async function saveCredentials() {
    const payload = {};
    CRED_KEYS.forEach(k => {
        const val = document.getElementById('cred-' + k).value.trim();
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
    document.getElementById('settingsDropdown').classList.remove('open');
    _lastFocusedElement = document.activeElement;
    document.getElementById('settingsModal').classList.add('open');
    document.getElementById('settingsLoading').classList.add('active');

    try {
        const resp = await fetch('/api/settings');
        const data = await resp.json();

        State.setDebugControlsAvailable(!!(data.debug_controls_available ?? true) && !(data.is_android ?? false));
        const debugRow = document.getElementById('debugModeRow');
        if (debugRow) debugRow.classList.toggle('hidden', !State.debugControlsAvailable);

        if (State.debugControlsAvailable) {
            const debugCheckbox = document.getElementById('settings-debug');
            debugCheckbox.checked = !!data.debug_mode;
            const debugStatus = document.getElementById('status-settings-debug');
            const debugLogPath = data.debug_log_path || 'debug.log';
            function updateDebugStatus() {
                const on = debugCheckbox.checked;
                debugStatus.textContent = on ? i18n('settings.debug_enabled', '✓ Enabled — log: {path}').replace('{path}', debugLogPath) : i18n('settings.debug_disabled', 'Disabled');
                debugStatus.className = 'cred-status ' + (on ? 'set' : 'unset');
            }
            updateDebugStatus();
            debugCheckbox.onchange = updateDebugStatus;
        }

        const modelStatus = document.getElementById('status-settings-model');
        modelStatus.textContent = i18n('settings.model_status', '✓ Using: {model}').replace('{model}', data.model || 'gpt-5.4-mini');
        modelStatus.className = 'cred-status set';

        const playlistSize = data.playlist_size || 10;
        document.getElementById('settings-playlist-size').value = playlistSize;
        const sizeStatus = document.getElementById('status-settings-playlist-size');
        sizeStatus.textContent = i18n('settings.playlist_size_status', '✓ Current: {size} tracks').replace('{size}', playlistSize);
        sizeStatus.className = 'cred-status set';

        const pct = data.new_artist_percentage || 30;
        document.getElementById('settings-new-artist-pct').value = pct;
        const pctStatus = document.getElementById('status-settings-new-artist-pct');
        pctStatus.textContent = i18n('settings.new_artist_pct_status', '✓ At least {pct}% of tracks from new artists').replace('{pct}', pct);
        pctStatus.className = 'cred-status set';


    } catch (e) { /* ignore */ }

    const select = document.getElementById('settings-model');
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

    document.getElementById('settingsLoading').classList.remove('active');
}

export async function saveSettings() {
    const payload = {};

    const modelSelect = document.getElementById('settings-model');
    if (modelSelect.value) {
        payload.model = modelSelect.value;
    }

    if (State.debugControlsAvailable) {
        payload.debug_mode = document.getElementById('settings-debug').checked;
    }

    const sizeVal = parseInt(document.getElementById('settings-playlist-size').value, 10);
    if (!isNaN(sizeVal) && sizeVal >= 10) {
        payload.playlist_size = sizeVal;
    }

    const pctVal = parseInt(document.getElementById('settings-new-artist-pct').value, 10);
    if (!isNaN(pctVal) && pctVal >= 1 && pctVal <= 100) {
        payload.new_artist_percentage = pctVal;
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
            fetchSettingsState().then(() => renderProviderPills());
        } else {
            const d = await resp.json();
            showAlert(i18n('msg.error_prefix', 'Error: {detail}').replace('{detail}', d.error || 'unknown'));
        }
    } catch (e) {
        showAlert(i18n('msg.network_error', 'Network error: {detail}').replace('{detail}', e.message));
    }
}

export async function openHelp() {
    document.getElementById('settingsDropdown').classList.remove('open');
    _lastFocusedElement = document.activeElement;
    _hideJumpBubble();
    _lockBodyScroll();
    document.getElementById('helpModal').classList.add('open');

    if (State.helpLoaded) return;

    try {
        const resp = await fetch('/api/help');
        const data = await resp.json();
        if (data.html) {
            document.getElementById('helpContent').innerHTML = sanitizeHtml(data.html);
            State.setHelpLoaded(true);

            // Wave 5: Show/hide fallback banner
            const banner = document.getElementById('helpFallbackBanner');
            if (banner) banner.classList.toggle('hidden', !data.fallback_used);

            const helpContent = document.getElementById('helpContent');
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
            document.getElementById('helpContent').innerHTML =
                '<p style="color:#e74c3c;">' + esc(i18n('help.load_failed', 'Could not load help content.')) + '</p>';
        }
    } catch (e) {
        document.getElementById('helpContent').innerHTML =
            '<p style="color:#e74c3c;">' + esc(i18n('help.load_error', 'Failed to load help: {detail}').replace('{detail}', e.message)) + '</p>';
    }
}

export async function openSectionHelp(anchor) {
    const overlay = document.getElementById('sectionHelpOverlay');
    const content = document.getElementById('sectionHelpContent');
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
    document.getElementById('sectionHelpOverlay').classList.remove('open');
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
    const modal = document.getElementById(id);
    modal.classList.add('open');
    requestAnimationFrame(() => _focusFirstInModal(modal));
}

export function closeModal(id) {
    document.getElementById(id).classList.remove('open');
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
    const banner = document.getElementById('helpFallbackBanner');
    if (banner) banner.classList.add('hidden');
}

/* ── Screenshot lightbox ── */

/** Minimum natural dimension (px) to show as expandable thumbnail. */
const LIGHTBOX_THRESHOLD = 300;

function _openScreenshotLightbox(imgEl) {
    const lb = document.getElementById('screenshotLightbox');
    const lbImg = document.getElementById('screenshotLightboxImg');
    if (!lb || !lbImg) return;
    lbImg.src = imgEl.src;
    lbImg.alt = imgEl.alt || 'Screenshot preview';
    lb.classList.add('open');
}

function _closeScreenshotLightbox() {
    const lb = document.getElementById('screenshotLightbox');
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
        const el = document.getElementById(id);
        if (el) el.addEventListener('click', _handleHelpImgClick);
    }

    // Close lightbox via close button
    const closeBtn = document.getElementById('screenshotLightboxClose');
    if (closeBtn) closeBtn.addEventListener('click', _closeScreenshotLightbox);

    // Close lightbox via click on backdrop or the image itself
    const lb = document.getElementById('screenshotLightbox');
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
        const el = document.getElementById(id);
        return el && el.classList.contains('open');
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
    document.getElementById('settingsDropdown').classList.remove('open');
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
    document.getElementById('quickstartModal').classList.add('open');
    requestAnimationFrame(() => _focusFirstInModal(document.getElementById('quickstartModal')));
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
 * Auto-show quickstart on page load (or first provider visit) if the user hasn't dismissed it.
 * @param {string} provider — "openai" or "spotify"
 */
export function maybeShowQuickstart(provider = 'openai') {
    if (!_isQuickstartDismissed(provider)) {
        // Defer so that the rest of init completes first
        setTimeout(() => openQuickstart(false), 0);
    }
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
    const lightbox = document.getElementById('screenshotLightbox');
    if (lightbox && lightbox.classList.contains('open')) {
        _closeScreenshotLightbox();
        return;
    }
    const sectionHelp = document.getElementById('sectionHelpOverlay');
    if (sectionHelp && sectionHelp.classList.contains('open')) {
        closeSectionHelp();
        return;
    }
    const quickstart = document.getElementById('quickstartModal');
    if (quickstart && quickstart.classList.contains('open')) {
        closeQuickstart();
        return;
    }
    for (const id of ['helpModal', 'credentialsModal', 'settingsModal']) {
        const el = document.getElementById(id);
        if (el && el.classList.contains('open')) {
            closeModal(id);
            return;
        }
    }
});

