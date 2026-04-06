import * as State from './state.js';
import { escHtml } from './ui.js';
import { i18n } from './i18n.js';

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
    pills.push(pill(State.openaiKeySet ? 'ok' : 'err', State.openaiKeySet ? i18n('pill.key_configured', 'Key configured') : i18n('pill.key_missing', 'Key missing')));
    pills.push(pill(State.profileTrained ? 'ok' : 'warn', State.profileTrained ? i18n('pill.profile_trained', 'Profile trained') : i18n('pill.not_trained', 'Not trained')));
    if (State.selectedModel) {
        pills.push(pill('ok', State.selectedModel));
    }
    el.innerHTML = pills.join('');
}

function renderSpotifyPills() {
    const el = document.getElementById('spotifyStatusPills');
    if (!el) return;
    const pills = [];
    const authStatus = State.spotifyAuthStatus;
    if (authStatus === 'authenticated') {
        pills.push(pill('ok', i18n('pill.connected', 'Connected')));
    } else if (authStatus === 'not_authenticated') {
        pills.push(pill('warn', i18n('pill.not_connected', 'Not connected')));
    } else if (authStatus === 'not_configured') {
        pills.push(pill('err', i18n('pill.credentials_missing', 'Credentials missing')));
    } else {
        pills.push(pill('warn', i18n('pill.status_unknown', 'Status unknown')));
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
