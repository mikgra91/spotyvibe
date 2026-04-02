import * as State from './state.js';
import { esc, attr } from './ui.js';

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
        const coverHtml = track.cover_url
            ? (track.track_id
                ? `<div class="track-cover-wrap" onclick="openPreviewOverlay('${attr(track.track_id)}','${attr(track.artist)} — ${attr(track.track)}')" title="Preview on Spotify">
                       <img class="track-cover" src="${attr(track.cover_url)}" alt="Album cover">
                       <span class="cover-play">▶</span>
                   </div>`
                : `<img class="track-cover" src="${attr(track.cover_url)}" alt="Album cover">`)
            : '';
        const noPreviewHtml = !track.track_id ? '<span class="track-no-preview">No preview</span>' : '';
        const spotifyLinks = [
            track.spotify_url ? `<a class="track-link" href="${attr(track.spotify_url)}" target="_blank" rel="noopener" title="Open track on Spotify">🎵</a>` : '',
            track.artist_url ? `<a class="track-link" href="${attr(track.artist_url)}" target="_blank" rel="noopener" title="Open artist on Spotify">🎤</a>` : '',
            track.album_url ? `<a class="track-link" href="${attr(track.album_url)}" target="_blank" rel="noopener" title="Open album on Spotify">💿</a>` : '',
        ].join('');

        li.innerHTML = `
            <div class="track-header">
                ${coverHtml}
                <div class="track-info">
                    <div class="track-name">${esc(track.artist)} — ${esc(track.track)}${spotifyLinks ? `<span class="track-links">${spotifyLinks}</span>` : ''}</div>
                    ${track.reason ? `<div class="track-reason">${esc(track.reason)}</div>` : ''}
                    ${noPreviewHtml}
                </div>
                <div class="track-actions">
                    <button class="btn btn-like"    onclick="toggleFeedback(${idx},'like')">👍 Like</button>
                    <button class="btn btn-dislike" onclick="toggleFeedback(${idx},'dislike')">👎 Dislike</button>
                    <button class="btn btn-remove"  onclick="removeTrack(${idx})">✕</button>
                </div>
            </div>
            <div class="feedback-form" id="form-${idx}">
                <div class="form-row">
                    <label for="artist-${idx}">Artist</label>
                    <input id="artist-${idx}" type="text" value="${attr(track.artist)}">
                </div>
                <div class="form-row">
                    <label for="title-${idx}">Track</label>
                    <input id="title-${idx}" type="text" value="${attr(track.track)}">
                    <div class="form-hint">Leave empty to apply feedback to the artist in general.</div>
                </div>
                <div class="form-row">
                    <label for="reason-${idx}">Reason (optional)</label>
                    <input id="reason-${idx}" type="text" placeholder="e.g. perfect energy, boring melody…">
                </div>
                <div class="form-actions">
                    <button class="btn" id="submitBtn-${idx}" onclick="submitFeedback(${idx})">Submit</button>
                    <button class="btn btn-cancel" onclick="closeFeedback(${idx})">Cancel</button>
                </div>
            </div>`;
        list.appendChild(li);
    });
}
