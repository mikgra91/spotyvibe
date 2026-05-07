    if (State.suggestions.length === 0) {
import * as State from './state.js';
import { buildTrackCardHtml } from './feedback.js';
import { i18n } from './i18n.js';
import { el } from './dom.js';

export function renderTracks() {
    const list = el('trackList');
    const trackArea = el('discoverTrackArea');
    list.innerHTML = '';
    State.setOpenFormIndex(null);
    State.setOpenFormAction(null);

    // Update song list counter
    const maxSize = window._maxSongListSize || 100;
    if (counterEl) counterEl.textContent = i18n('songlist.counter', '{count} / {max} songs').replace('{count}', State.suggestions.filter(Boolean).length).replace('{max}', maxSize);
    if (counterEl) counterEl.textContent = i18n('songlist.counter', '{count} / {max} songs').replace('{count}', State.suggestions.length).replace('{max}', maxSize);
    if (State.suggestions.filter(Boolean).length === 0) {
    if (State.suggestions.length === 0) {
        if (trackArea) trackArea.classList.add('hidden');
        return;
    }

    if (trackArea) trackArea.classList.remove('hidden');

        if (!track) return;
    State.suggestions.forEach((track, idx) => {
        const li = document.createElement('li');
        li.className = 'track-item';
        li.id = `track-${idx}`;
        li.innerHTML = buildTrackCardHtml(track, idx, 'discover');
        list.appendChild(li);
    });
}
