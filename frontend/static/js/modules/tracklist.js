import * as State from './state.js';
import { buildTrackCardHtml } from './feedback.js';
import { i18n } from './i18n.js';

export function renderTracks() {
    const list = document.getElementById('trackList');
    const trackArea = document.getElementById('discoverTrackArea');
    list.innerHTML = '';
    State.setOpenFormIndex(null);
    State.setOpenFormAction(null);

    // Update song list counter
    const maxSize = window._maxSongListSize || 100;
    const counterEl = document.getElementById('songlistCounter');
    if (counterEl) counterEl.textContent = i18n('songlist.counter', '{count} / {max} songs').replace('{count}', State.suggestions.length).replace('{max}', maxSize);

    if (State.suggestions.length === 0) {
        if (trackArea) trackArea.classList.add('hidden');
        return;
    }

    if (trackArea) trackArea.classList.remove('hidden');

    State.suggestions.forEach((track, idx) => {
        const li = document.createElement('li');
        li.className = 'track-item';
        li.id = `track-${idx}`;
        li.innerHTML = buildTrackCardHtml(track, idx, 'discover');
        list.appendChild(li);
    });
}
