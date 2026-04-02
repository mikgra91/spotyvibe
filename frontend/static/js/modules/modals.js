import * as State from './state.js';
import { showStatus, showToast, esc, sanitizeHtml } from './ui.js';
import { checkCredentialStatus, checkSpotifyAuth, fetchSettingsState } from './auth.js';
import { renderComponentWarnings } from './warnings.js';
import { renderProviderPills } from './spotify-metadata.js';

const CRED_KEYS = ['OPENAI_API_KEY', 'SPOTIPY_CLIENT_ID', 'SPOTIPY_CLIENT_SECRET'];

export async function clearCredential(key) {
    if (!confirm('Remove ' + key + '?')) return;

    try {
        const resp = await fetch('/api/settings/credentials', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ [key]: '' }),
        });
        if (resp.ok) {
            const el = document.getElementById('status-' + key);
            el.textContent = '✗ Not set';
            el.className = 'cred-status unset';
            document.getElementById('clear-' + key).classList.add('hidden');
            document.getElementById('cred-' + key).value = '';

            await Promise.all([checkCredentialStatus(), checkSpotifyAuth()]);
            renderComponentWarnings();

            showToast(key + ' cleared.', 'info');
        }
    } catch (e) {
        alert('Network error: ' + e.message);
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
                el.textContent = '✓ Set (' + info.masked + ')';
                el.className = 'cred-status set';
                clearBtn.classList.remove('hidden');
            } else {
                el.textContent = '✗ Not set';
                el.className = 'cred-status unset';
                clearBtn.classList.add('hidden');
            }
        });
    } catch (e) { /* ignore — status will just be empty */ }

    document.getElementById('credentialsModal').classList.add('open');
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
            showStatus('✅ Credentials saved.', 'success');
            await Promise.all([checkCredentialStatus(), checkSpotifyAuth()]);
            renderComponentWarnings();
        } else {
            const d = await resp.json();
            alert('Error: ' + (d.error || 'unknown'));
        }
    } catch (e) {
        alert('Network error: ' + e.message);
    }
}

export async function openSettings() {
    document.getElementById('settingsDropdown').classList.remove('open');
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
                debugStatus.textContent = on ? '✓ Enabled — log: ' + debugLogPath : 'Disabled';
                debugStatus.className = 'cred-status ' + (on ? 'set' : 'unset');
            }
            updateDebugStatus();
            debugCheckbox.onchange = updateDebugStatus;
        }

        const modelStatus = document.getElementById('status-settings-model');
        modelStatus.textContent = '✓ Using: ' + (data.model || 'gpt-4.1-mini');
        modelStatus.className = 'cred-status set';

        const playlistSize = data.playlist_size || 10;
        document.getElementById('settings-playlist-size').value = playlistSize;
        const sizeStatus = document.getElementById('status-settings-playlist-size');
        sizeStatus.textContent = '✓ Current: ' + playlistSize + ' tracks';
        sizeStatus.className = 'cred-status set';

        const pct = data.new_artist_percentage || 30;
        document.getElementById('settings-new-artist-pct').value = pct;
        const pctStatus = document.getElementById('status-settings-new-artist-pct');
        pctStatus.textContent = '✓ At least ' + pct + '% of tracks from new artists';
        pctStatus.className = 'cred-status set';

        const lang = data.gpt_language || 'English';
        const langSelect = document.getElementById('settings-gpt-language');
        let found = false;
        for (const opt of langSelect.options) {
            if (opt.value === lang) { opt.selected = true; found = true; break; }
        }
        if (!found) {
            const opt = document.createElement('option');
            opt.value = lang; opt.textContent = lang; opt.selected = true;
            langSelect.appendChild(opt);
        }
        document.getElementById('status-settings-gpt-language').textContent = '✓ ' + lang;
        document.getElementById('status-settings-gpt-language').className = 'cred-status set';

    } catch (e) { /* ignore */ }

    const select = document.getElementById('settings-model');
    select.innerHTML = '<option value="">Loading models…</option>';

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
            select.innerHTML = '<option value="">' + (data.error ? 'Enter API key first' : 'No models available') + '</option>';
        }
    } catch (e) {
        select.innerHTML = '<option value="">Could not load models</option>';
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

    const langVal = document.getElementById('settings-gpt-language').value;
    if (langVal) payload.gpt_language = langVal;

    try {
        const resp = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (resp.ok) {
            closeModal('settingsModal');
            showStatus('✅ Settings saved.', 'success');
            fetchSettingsState().then(() => renderProviderPills());
        } else {
            const d = await resp.json();
            alert('Error: ' + (d.error || 'unknown'));
        }
    } catch (e) {
        alert('Network error: ' + e.message);
    }
}

export async function openHelp() {
    document.getElementById('settingsDropdown').classList.remove('open');
    document.getElementById('helpModal').classList.add('open');

    if (State.helpLoaded) return;

    try {
        const resp = await fetch('/api/help');
        const data = await resp.json();
        if (data.html) {
            document.getElementById('helpContent').innerHTML = sanitizeHtml(data.html);
            State.setHelpLoaded(true);
        } else {
            document.getElementById('helpContent').innerHTML =
                '<p style="color:#e74c3c;">Could not load help content.</p>';
        }
    } catch (e) {
        document.getElementById('helpContent').innerHTML =
            '<p style="color:#e74c3c;">Failed to load help: ' + esc(e.message) + '</p>';
    }
}

export async function openSectionHelp(anchor) {
    const overlay = document.getElementById('sectionHelpOverlay');
    const content = document.getElementById('sectionHelpContent');
    content.innerHTML = '<p class="help-loading-text">Loading…</p>';
    overlay.classList.add('open');

    try {
        const resp = await fetch('/api/help/section/' + encodeURIComponent(anchor));
        const data = await resp.json();
        if (data.html) {
            content.innerHTML = sanitizeHtml(data.html);
        } else {
            content.innerHTML =
                '<p style="color:#e74c3c;">Section not found.</p>';
        }
    } catch (e) {
        content.innerHTML =
            '<p style="color:#e74c3c;">Failed to load help: ' + esc(e.message) + '</p>';
    }
}

export function closeSectionHelp() {
    document.getElementById('sectionHelpOverlay').classList.remove('open');
}

export async function openDataDir() {
    try {
        const resp = await fetch('/api/settings/open-data-dir', { method: 'POST' });
        const data = await resp.json();
        if (!resp.ok) {
            showToast(data.error || 'Could not open folder.', 'error');
        }
    } catch (e) {
        showToast('Network error: ' + e.message, 'error');
    }
}

export function closeModal(id) {
    document.getElementById(id).classList.remove('open');
}
