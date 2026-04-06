import * as State from './state.js';
import { renderComponentWarnings } from './warnings.js';
import { showToast, showAlert } from './ui.js';
import { i18n } from './i18n.js';

export async function checkCredentialStatus() {
    try {
        const resp = await fetch('/api/settings/credentials');
        const data = await resp.json();
        State.setOpenaiKeySet(!!(data.OPENAI_API_KEY && data.OPENAI_API_KEY.is_set));
    } catch (e) {
        State.setOpenaiKeySet(false);
    }
}

export async function fetchSettingsState() {
    try {
        const resp = await fetch('/api/settings');
        const data = await resp.json();
        State.setSelectedModel(data.model || '');
        State.setGptLanguage(data.gpt_language || '');
    } catch (e) { /* ignore */ }
}

export async function checkSpotifyAuth() {
    try {
        const resp = await fetch('/api/spotify/status');
        const data = await resp.json();
        const valid = ['authenticated', 'not_authenticated', 'not_configured'];
        State.setSpotifyAuthStatus(valid.includes(data.status) ? data.status : 'unknown');
    } catch (e) {
        State.setSpotifyAuthStatus('unknown');
    }
}

export function connectSpotify() {
    // pywebview desktop: open OAuth in a managed child window (keeps main window intact)
    if (window.pywebview && window.pywebview.api && window.pywebview.api.open_spotify_auth) {
        window.pywebview.api.open_spotify_auth();
        return;
    }
    // Android WebView: navigate in-window (no popup)
    if (/; wv\)/.test(navigator.userAgent)) {
        window.location.href = '/api/spotify/auth';
        return;
    }
    const w = 500, h = 700;
    const left = screen.width / 2 - w / 2;
    const top = screen.height / 2 - h / 2;
    window.open(
        '/api/spotify/auth',
        'spotify-auth',
        `width=${w},height=${h},left=${left},top=${top}`
    );
}

export async function toggleSpotifyConnection() {
    document.getElementById('settingsDropdown').classList.remove('open');
    if (State.spotifyAuthStatus === 'authenticated') {
        try {
            await fetch('/api/spotify/disconnect', { method: 'POST' });
            showToast(i18n('msg.spotify_disconnected', 'Spotify disconnected.'), 'info');
            await checkSpotifyAuth();
            renderComponentWarnings();
        } catch (e) {
            showAlert(i18n('msg.network_error', 'Network error: {detail}').replace('{detail}', e.message));
        }
    } else {
        connectSpotify();
    }
}
