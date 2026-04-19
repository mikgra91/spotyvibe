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
}

function openCredentials() {
    import('./modals.js').then(m => m.openCredentials());
}
