import * as State from './state.js';
import { showToast, showAlert, esc, attr } from './ui.js';

/**
 * Build the inner HTML for a track card (shared by discover and review lists).
 * @param {Object} track - Track object with artist, track, cover_url, track_id, etc.
 * @param {number} idx - Index in the source array.
 * @param {string} source - 'discover' or 'review' — determines which JS functions to call.
 */
export function buildTrackCardHtml(track, idx, source = 'discover') {
    const feedbackFn = source === 'review' ? 'toggleReviewFeedback' : 'toggleFeedback';
    const removeFn = source === 'review' ? 'dismissReviewTrack' : 'removeTrack';
    const submitFn = source === 'review' ? 'submitReviewFeedback' : 'submitFeedback';
    const closeFn = source === 'review' ? 'closeReviewFeedback' : 'closeFeedback';
    const prefix = source === 'review' ? 'review' : '';
    const formId = prefix ? `review-form-${idx}` : `form-${idx}`;
    const artistId = prefix ? `review-artist-${idx}` : `artist-${idx}`;
    const titleId = prefix ? `review-title-${idx}` : `title-${idx}`;
    const reasonId = prefix ? `review-reason-${idx}` : `reason-${idx}`;
    const submitBtnId = prefix ? `review-submitBtn-${idx}` : `submitBtn-${idx}`;

    const coverHtml = track.cover_url
        ? (track.track_id
            ? `<div class="track-cover-wrap" onclick="openPreviewOverlay('${attr(track.track_id)}','${attr(track.artist)} — ${attr(track.track)}','${source}')" title="Preview on Spotify">
                   <img class="track-cover" src="${attr(track.cover_url)}" alt="Album cover" loading="lazy">
                   <span class="cover-play">▶</span>
               </div>`
            : `<img class="track-cover" src="${attr(track.cover_url)}" alt="Album cover" loading="lazy">`)
        : '';
    const noPreviewHtml = !track.track_id ? '<span class="track-no-preview">No preview</span>' : '';
    const spotifyLinks = [
        track.spotify_url ? `<a class="track-link" href="${attr(track.spotify_url)}" target="_blank" rel="noopener" title="Open track on Spotify">🎵</a>` : '',
        track.artist_url ? `<a class="track-link" href="${attr(track.artist_url)}" target="_blank" rel="noopener" title="Open artist on Spotify">🎤</a>` : '',
        track.album_url ? `<a class="track-link" href="${attr(track.album_url)}" target="_blank" rel="noopener" title="Open album on Spotify">💿</a>` : '',
    ].join('');

    return `
        <div class="track-header">
            ${coverHtml}
            <div class="track-info">
                <div class="track-name">${esc(track.artist)} — ${esc(track.track)}${spotifyLinks ? `<span class="track-links">${spotifyLinks}</span>` : ''}</div>
                ${track.reason ? `<div class="track-reason">${esc(track.reason)}</div>` : ''}
                ${noPreviewHtml}
            </div>
            <div class="track-actions">
                <button class="btn btn-like"    onclick="${feedbackFn}(${idx},'like')">👍 Like</button>
                <button class="btn btn-dislike" onclick="${feedbackFn}(${idx},'dislike')">👎 Dislike</button>
                <button class="btn btn-remove"  onclick="${removeFn}(${idx})">✕</button>
            </div>
        </div>
        <div class="feedback-form" id="${formId}">
            <div class="form-row">
                <label for="${artistId}">Artist</label>
                <input id="${artistId}" type="text" value="${attr(track.artist)}">
            </div>
            <div class="form-row">
                <label for="${titleId}">Track</label>
                <input id="${titleId}" type="text" value="${attr(track.track)}">
                <div class="form-hint">Leave empty to apply feedback to the artist in general.</div>
            </div>
            <div class="form-row">
                <label for="${reasonId}">Reason (optional)</label>
                <input id="${reasonId}" type="text" placeholder="e.g. perfect energy, boring melody…">
            </div>
            <div class="form-actions">
                <button class="btn" id="${submitBtnId}" onclick="${submitFn}(${idx})">Submit</button>
                <button class="btn btn-cancel" onclick="${closeFn}(${idx})">Cancel</button>
            </div>
        </div>`;
}

export function toggleFeedback(idx, action) {
    if (State.openFormIndex !== null && State.openFormIndex !== idx) {
        closeFeedback(State.openFormIndex);
    }

    const form = document.getElementById(`form-${idx}`);
    const isOpen = form.classList.contains('open');

    if (isOpen && State.openFormAction === action) {
        closeFeedback(idx);
        return;
    }

    form.classList.add('open');
    State.setOpenFormIndex(idx);
    State.setOpenFormAction(action);

    const submitBtn = document.getElementById(`submitBtn-${idx}`);
    if (action === 'like') {
        submitBtn.textContent = '👍 Submit';
        submitBtn.className = 'btn btn-submit-like';
    } else {
        submitBtn.textContent = '👎 Submit';
        submitBtn.className = 'btn btn-submit-dislike';
    }
}

export function closeFeedback(idx) {
    const form = document.getElementById(`form-${idx}`);
    if (form) form.classList.remove('open');
    if (State.openFormIndex === idx) {
        State.setOpenFormIndex(null);
        State.setOpenFormAction(null);
    }
}

export async function submitFeedback(idx) {
    const artist = document.getElementById(`artist-${idx}`).value.trim();
    const track  = document.getElementById(`title-${idx}`).value.trim();
    const reason = document.getElementById(`reason-${idx}`).value.trim();

    if (!artist) { showAlert('Artist is required.'); return; }

    const submitBtn = document.getElementById(`submitBtn-${idx}`);
    submitBtn.disabled = true;
    submitBtn.textContent = '…';

    try {
        const resp = await fetch('/api/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: State.openFormAction,
                artist,
                track:  track  || null,
                reason: reason || null,
            }),
        });

        if (!resp.ok) {
            const data = await resp.json();
            showAlert('Error: ' + (data.error || 'unknown'));
            return;
        }

        const data = await resp.json();
        const trackLabel = track ? ` — ${track}` : '';

        if (State.openFormAction === 'dislike') {
            const removed = data.removal && data.removal.removed;
            const msg = removed
                ? `👎 Disliked & removed from playlist: ${artist}${trackLabel}`
                : `👎 Disliked: ${artist}${trackLabel}`;
            showToast(msg);
        } else {
            showToast(`👍 Liked: ${artist}${trackLabel}`);
        }

        const fbTrack = State.suggestions[idx];
        animateRemove(idx);

        if (fbTrack) {
            fetch('/api/songlist/track', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ artist: fbTrack.artist, track: fbTrack.track }),
            }).catch(() => {});
        }
    } catch (e) {
        showAlert('Network error: ' + e.message);
    } finally {
        submitBtn.disabled = false;
    }
}

export async function removeTrack(idx) {
    const track = State.suggestions[idx];
    if (!track) { animateRemove(idx); return; }

    try {
        const resp = await fetch('/api/remove', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ artist: track.artist, track: track.track }),
        });
        const data = await resp.json();
        const msg = data.removed
            ? `Removed from playlist: ${track.artist} — ${track.track}`
            : `Removed: ${track.artist} — ${track.track}`;
        showToast(msg);
    } catch (e) {
        /* Network error — still remove from UI */
    }

    animateRemove(idx);

    if (track) {
        fetch('/api/songlist/track', {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ artist: track.artist, track: track.track }),
        }).catch(() => {});
    }
}

export function animateRemove(idx) {
    const el = document.getElementById(`track-${idx}`);
    if (!el) return;
    el.style.opacity = '0';
    el.style.transform = 'translateX(40px)';
    setTimeout(() => el.remove(), 300);

    State.spliceSuggestion(idx);

    if (State.openFormIndex === idx) {
        State.setOpenFormIndex(null);
        State.setOpenFormAction(null);
    }
}
