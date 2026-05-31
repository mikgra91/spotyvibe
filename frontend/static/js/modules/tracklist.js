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
    const counterEl = el('songlistCounter');
    if (counterEl) counterEl.textContent = i18n('songlist.counter', '{count} / {max} songs').replace('{count}', State.suggestions.filter(Boolean).length).replace('{max}', maxSize);

    // The Apply/Clear actions row is tied strictly to having tracks — the
    // surrounding trackArea can still be force-shown by status messages
    // (e.g. "Settings saved"), so the row needs its own visibility or the
    // buttons appear with an empty list.
    const actionsRow = el('discoverTrackActions');
    const hasTracks = State.suggestions.filter(Boolean).length > 0;
    if (actionsRow) actionsRow.classList.toggle('hidden', !hasTracks);

    if (!hasTracks) {
        if (trackArea) trackArea.classList.add('hidden');
        return;
    }

    if (trackArea) trackArea.classList.remove('hidden');

    State.suggestions.forEach((track, idx) => {
        if (!track) return;
        const li = document.createElement('li');
        // Bug-1 fix (2026-05-30): preserve the liked-glow across re-renders.
        li.className = 'track-item' + (track._liked ? ' liked' : '');
        li.id = `track-${idx}`;
        li.innerHTML = buildTrackCardHtml(track, idx, 'discover');
        list.appendChild(li);
    });
}
