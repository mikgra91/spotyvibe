import * as State from './state.js';
import { i18n } from './i18n.js';
import { renderProviderPills } from './provider-pills.js';
import { el } from './dom.js';

export function renderComponentWarnings() {
    renderProviderPills();
    const trainWarn = el('trainWarn');
    const trainBtn = el('trainSendBtn');
    const trainToggle = el('trainToggleBtn');

    if (!State.openaiKeySet) {
        trainWarn.className = 'component-warn';
        trainWarn.textContent = '';
        trainWarn.append(i18n('warn.openai_missing_prefix', '⚠️ OpenAI API key is missing. Open '));
        const trainLink = document.createElement('a');
        trainLink.textContent = '⚙️ ' + i18n('nav.settings', 'Settings');
        trainLink.style.cursor = 'pointer';
        trainLink.addEventListener('click', openCredentials);
        trainWarn.append(trainLink, i18n('warn.openai_missing_suffix', ' to enter it.'));
        trainBtn.disabled = true;
        trainToggle.disabled = true;
    } else {
        trainWarn.className = 'hidden';
        trainBtn.disabled = false;
        trainToggle.disabled = false;
    }

    const runWarn = el('runWarn');
    const runBtn = el('runBtn');

    function _warnLink(text, handler) {
        const a = document.createElement('a');
        a.textContent = text;
        a.style.cursor = 'pointer';
        a.addEventListener('click', handler);
        return a;
    }

    const warnFragments = [];
    if (!State.openaiKeySet) {
        const f = document.createDocumentFragment();
        f.append(i18n('warn.openai_missing_run', 'OpenAI API key is missing — open '), _warnLink('⚙️ ' + i18n('nav.settings', 'Settings'), openCredentials), '.');
        warnFragments.push(f);
    }
    if (State.spotifyAuthStatus === 'not_configured') {
        const f = document.createDocumentFragment();
        f.append(i18n('warn.spotify_missing_run', 'Spotify credentials are missing — open '), _warnLink('⚙️ ' + i18n('nav.settings', 'Settings'), openCredentials), '.');
        warnFragments.push(f);
    } else if (State.spotifyAuthStatus === 'not_authenticated') {
        const f = document.createDocumentFragment();
        f.append(i18n('warn.spotify_login_required', 'Spotify login required — '), _warnLink(i18n('warn.connect_spotify', 'Connect to Spotify'), () => import('./auth.js').then(m => m.connectSpotify())), '.');
        warnFragments.push(f);
    }

    if (warnFragments.length > 0) {
        runWarn.className = 'component-warn';
        runWarn.textContent = '';
        warnFragments.forEach((frag, i) => {
            if (i > 0) runWarn.append(document.createElement('br'));
            runWarn.append('⚠️ ', frag);
        });
        runBtn.disabled = true;
    } else {
        runWarn.className = 'hidden';
        runBtn.disabled = false;
    }

    const spotifyLabel = el('spotifyToggleLabel');
    if (spotifyLabel) {
        if (State.spotifyAuthStatus === 'authenticated') {
            spotifyLabel.setAttribute('data-i18n', 'nav.disconnect_spotify');
            spotifyLabel.textContent = i18n('nav.disconnect_spotify', 'Disconnect Spotify');
        } else {
            spotifyLabel.setAttribute('data-i18n', 'nav.connect_spotify');
            spotifyLabel.textContent = i18n('nav.connect_spotify', 'Connect Spotify');
        }
    }

    // U6 (2026-05-07): live Spotify-connected badge in the header. Mirrors
    // State.spotifyAuthStatus into a class on the pill so the green/red
    // dot reflects the current session state. Refreshed on every
    // checkSpotifyAuth() call (page load, focus, visibilitychange — see U1).
    const pill = el('spotifyStatusPill');
    if (pill) {
        const status = State.spotifyAuthStatus;
        let stateClass, labelKey, labelEn;
        if (status === 'authenticated') {
            stateClass = 'spotify-status-connected';
            labelKey = 'nav.spotify_status_connected';
            labelEn = 'Spotify connected';
        } else if (status === 'not_authenticated' || status === 'not_configured') {
            stateClass = 'spotify-status-disconnected';
            labelKey = 'nav.spotify_status_disconnected';
            labelEn = 'Spotify not connected';
        } else {
            stateClass = 'spotify-status-unknown';
            labelKey = 'nav.spotify_status_unknown';
            labelEn = 'Spotify status unknown';
        }
        pill.classList.remove('spotify-status-connected', 'spotify-status-disconnected', 'spotify-status-unknown');
        pill.classList.add(stateClass);
        const localized = i18n(labelKey, labelEn);
        pill.setAttribute('aria-label', localized);
        pill.setAttribute('title', localized);
        pill.setAttribute('data-i18n-attr', `aria-label:${labelKey},title:${labelKey}`);
    }
}

function openCredentials() {
    import('./modals.js').then(m => m.openCredentials());
}
