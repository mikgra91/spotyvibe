import * as State from './state.js';
import { buildTrackCardHtml } from './feedback.js';

export function renderTracks() {
    const list = document.getElementById('trackList');
    list.innerHTML = '';
    State.setOpenFormIndex(null);
    State.setOpenFormAction(null);

    // Update song list counter
    const maxSize = window._maxSongListSize || 100;
    const counterEl = document.getElementById('songlistCounter');
    if (counterEl) counterEl.textContent = `${State.suggestions.length} / ${maxSize} songs`;

    if (State.suggestions.length === 0) {
        return;
    }

    State.suggestions.forEach((track, idx) => {
        const li = document.createElement('li');
        li.className = 'track-item';
        li.id = `track-${idx}`;
        li.innerHTML = buildTrackCardHtml(track, idx, 'discover');
        list.appendChild(li);
    });
}
