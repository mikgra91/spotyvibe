import * as State from './state.js';
import { escHtml } from './ui.js';
import { i18n } from './i18n.js';
import { el } from './dom.js';

// Provider summary pill rendering
export function renderProviderPills() {
    renderOpenaiPills();
    renderSpotifyPills();
    renderDepChips();
}

function renderOpenaiPills() {
    const container = el('openaiStatusPills');
    if (!container) return;
    const pills = [];
    // Only show model pill — clickable to open settings
    if (State.selectedModel) {
        const label = `${i18n('pill.used_model', 'Model')}: ${escHtml(State.selectedModel)}`;
        pills.push(`<button class="status-pill status-pill--ok status-pill--clickable" onclick="openSettings()" title="${escHtml(i18n('pill.change_model', 'Change model'))}">${label}</button>`);
    }
    container.innerHTML = pills.join('');
}

function renderSpotifyPills() {
    const container = el('spotifyStatusPills');
    if (!container) return;
    const pills = [];
    const authStatus = State.spotifyAuthStatus;
    if (authStatus === 'authenticated') {
        pills.push(pill('ok', i18n('pill.spotify_connected', 'Spotify connected')));
    } else if (authStatus === 'not_authenticated') {
        pills.push(`<button class="status-pill status-pill--warn status-pill--clickable" onclick="connectSpotify()" title="${escHtml(i18n('pill.click_to_connect', 'Click to connect'))}">${escHtml(i18n('pill.spotify_not_connected', 'Spotify not connected'))}</button>`);
    } else if (authStatus === 'not_configured') {
        pills.push(`<button class="status-pill status-pill--err status-pill--clickable" onclick="openCredentials()" title="${escHtml(i18n('pill.click_to_setup', 'Click to set up'))}">${escHtml(i18n('pill.credentials_missing', 'Credentials missing'))}</button>`);
    } else {
        pills.push(pill('warn', i18n('pill.status_unknown', 'Status unknown')));
    }
    container.innerHTML = pills.join('');
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
