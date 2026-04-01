import * as State from './state.js';
import { renderComponentWarnings } from './warnings.js';
import { showToast } from './ui.js';

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
            showToast('Spotify disconnected.', 'info');
            await checkSpotifyAuth();
            renderComponentWarnings();
        } catch (e) {
            alert('Network error: ' + e.message);
        }
    } else {
        connectSpotify();
    }
}
