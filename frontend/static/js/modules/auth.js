import * as State from './state.js';
import { renderComponentWarnings } from './warnings.js';
import { showToast, showAlert } from './ui.js';
import { i18n } from './i18n.js';
import { el } from './dom.js';

export async function checkCredentialStatus() {
    try {
        const resp = await fetch('/api/settings/credentials');
        const data = await resp.json();
        const physicalKeySet = !!(data.OPENAI_API_KEY && data.OPENAI_API_KEY.is_set);
        // Local providers (Ollama, LM Studio) don't need an API key
        State.setOpenaiKeySet(physicalKeySet || !State.llmApiKeyRequired);
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
        // Wave 4: track whether the current provider needs an API key
        if (data.llm_api_key_required !== undefined) {
            State.setLlmApiKeyRequired(data.llm_api_key_required);
        }
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
        _startSpotifyAuthPoll();
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
    // 2026-05-12: belt-and-suspenders fallback. The popup posts
    // `spotify-auth-complete` to window.opener on success, but that message
    // can be silently dropped (popup blocker rewriting target=_blank,
    // cross-origin Referrer-Policy on the Spotify redirect, COOP headers,
    // browsers severing window.opener for noopener popups, etc.). Without
    // this poll the status pill stays stuck on "Spotify not connected"
    // even after a successful login. Poll /api/spotify/status until it
    // flips, then refresh the pill via the shared completion handler.
    _startSpotifyAuthPoll();
}

let _spotifyAuthPollTimer = null;
function _startSpotifyAuthPoll() {
    if (_spotifyAuthPollTimer) return; // already polling
    const startedAt = Date.now();
    const TIMEOUT_MS = 90000;
    const INTERVAL_MS = 2000;
    _spotifyAuthPollTimer = setInterval(async () => {
        if (Date.now() - startedAt > TIMEOUT_MS) {
            clearInterval(_spotifyAuthPollTimer);
            _spotifyAuthPollTimer = null;
            return;
        }
        try {
            const resp = await fetch('/api/spotify/status');
            const data = await resp.json();
            // Stop polling once we have a definitive answer. The previous
            // guard (`State.spotifyAuthStatus !== 'authenticated'`) failed
            // when the postMessage handler updated state first, leaving the
            // timer running for the full 90s timeout and hammering Spotify.
            if (data.status === 'authenticated' || data.status === 'not_configured') {
                clearInterval(_spotifyAuthPollTimer);
                _spotifyAuthPollTimer = null;
                if (data.status === 'authenticated' && State.spotifyAuthStatus !== 'authenticated') {
                    await onSpotifyAuthCompleted();
                }
            }
        } catch (_) { /* network blip — retry next tick */ }
    }, INTERVAL_MS);
}

/** Shared handler invoked when Spotify OAuth completes (postMessage OR poll). */
export async function onSpotifyAuthCompleted() {
    await checkSpotifyAuth();
    renderComponentWarnings();
    if (typeof window.refreshGettingStarted === 'function') window.refreshGettingStarted();
}

export async function toggleSpotifyConnection() {
    el('settingsDropdown').classList.remove('open');
    if (State.spotifyAuthStatus === 'authenticated') {
        try {
            await fetch('/api/spotify/disconnect', { method: 'POST' });
            showToast(i18n('msg.spotify_disconnected', 'Spotify disconnected.'), 'info');
            await checkSpotifyAuth();
            renderComponentWarnings();
            if (typeof window.refreshGettingStarted === 'function') window.refreshGettingStarted();
        } catch (e) {
            showAlert(i18n('msg.network_error', 'Network error: {detail}').replace('{detail}', e.message));
        }
    } else {
        connectSpotify();
    }
}
