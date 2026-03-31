import * as State from './state.js';

export function renderComponentWarnings() {
    const trainWarn = document.getElementById('trainWarn');
    const trainBtn = document.getElementById('trainSendBtn');
    const trainToggle = document.getElementById('trainToggleBtn');

    if (!State.openaiKeySet) {
        trainWarn.className = 'component-warn';
        trainWarn.textContent = '';
        trainWarn.append('⚠️ OpenAI API key is missing. Open ');
        const trainLink = document.createElement('a');
        trainLink.textContent = '⚙️ Settings';
        trainLink.style.cursor = 'pointer';
        trainLink.addEventListener('click', openCredentials);
        trainWarn.append(trainLink, ' to enter it.');
        trainBtn.disabled = true;
        trainToggle.disabled = true;
    } else {
        trainWarn.className = 'hidden';
        trainBtn.disabled = false;
        trainToggle.disabled = false;
    }

    const runWarn = document.getElementById('runWarn');
    const runBtn = document.getElementById('runBtn');

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
        f.append('OpenAI API key is missing — open ', _warnLink('⚙️ Settings', openCredentials), '.');
        warnFragments.push(f);
    }
    if (State.spotifyAuthStatus === 'not_configured') {
        const f = document.createDocumentFragment();
        f.append('Spotify credentials are missing — open ', _warnLink('⚙️ Settings', openCredentials), '.');
        warnFragments.push(f);
    } else if (State.spotifyAuthStatus === 'not_authenticated') {
        const f = document.createDocumentFragment();
        f.append('Spotify login required — ', _warnLink('Connect to Spotify', () => import('./auth.js').then(m => m.connectSpotify())), '.');
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

    const spotifyBtn = document.getElementById('spotifyToggleBtn');
    if (State.spotifyAuthStatus === 'authenticated') {
        spotifyBtn.textContent = '🔌 Disconnect Spotify';
    } else {
        spotifyBtn.textContent = '🔌 Connect Spotify';
    }
}

function openCredentials() {
    import('./modals.js').then(m => m.openCredentials());
}
