import * as State from './state.js';
import { escHtml } from './ui.js';

// Provider summary pill rendering
export function renderProviderPills() {
    renderOpenaiPills();
    renderSpotifyPills();
    renderDepChips();
}

function renderOpenaiPills() {
    const el = document.getElementById('openaiStatusPills');
    if (!el) return;
    const pills = [];
    pills.push(pill(State.openaiKeySet ? 'ok' : 'err', State.openaiKeySet ? 'Key configured' : 'Key missing'));
    pills.push(pill(State.profileTrained ? 'ok' : 'warn', State.profileTrained ? 'Profile trained' : 'Not trained'));
    if (State.selectedModel) {
        pills.push(pill('ok', State.selectedModel));
    }
    if (State.gptLanguage) {
        pills.push(pill('ok', State.gptLanguage));
    }
    el.innerHTML = pills.join('');
}

function renderSpotifyPills() {
    const el = document.getElementById('spotifyStatusPills');
    if (!el) return;
    const pills = [];
    const authStatus = State.spotifyAuthStatus;
    if (authStatus === 'authenticated') {
        pills.push(pill('ok', 'Connected'));
    } else if (authStatus === 'not_authenticated') {
        pills.push(pill('warn', 'Not connected'));
    } else if (authStatus === 'not_configured') {
        pills.push(pill('err', 'Credentials missing'));
    } else {
        pills.push(pill('warn', 'Status unknown'));
    }
    el.innerHTML = pills.join('');
}

function renderDepChips() {
    const openaiDot = document.querySelector('#depOpenai .dep-dot');
    const spotifyDot = document.querySelector('#depSpotify .dep-dot');
    if (openaiDot) {
        const ok = State.openaiKeySet && State.profileTrained;
        openaiDot.className = 'dep-dot ' + (ok ? 'dep-dot--ok' : 'dep-dot--warn');
    }
    if (spotifyDot) {
        const ok = State.spotifyAuthStatus === 'authenticated';
        spotifyDot.className = 'dep-dot ' + (ok ? 'dep-dot--ok' : 'dep-dot--warn');
    }
}

function pill(type, label) {
    return `<span class="status-pill status-pill--${type}">${escHtml(label)}</span>`;
}
