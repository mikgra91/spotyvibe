import * as State from './state.js';
import { showToast, showAlert, esc, attr } from './ui.js';
import { i18n } from './i18n.js';
import { buildRationaleHtml } from './rationale.js';
import { resetDashboard } from './taste_dashboard.js';
import { el } from './dom.js';
import { postFeedback, postRemove } from './feedback-api.js';
import { onExternalTrackRemoved } from './preview.js';

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
            // Pass only the numeric index + the controlled source literal into
            // the inline handler. Embedding untrusted artist/track/track_id in
            // an inline onclick is an XSS vector: attr() escapes quotes to HTML
            // entities, but the HTML parser decodes them back before the JS
            // string is evaluated, so a crafted name could break out of the JS
            // literal. openPreviewByIndex re-resolves the track from State.
            ? `<div class="track-cover-wrap" onclick="openPreviewByIndex(${idx},'${source}')" title="${attr(i18n('feedback.preview_on_spotify', 'Preview on Spotify'))}">
                   <img class="track-cover" src="${attr(track.cover_url)}" alt="${attr(i18n('feedback.album_cover', 'Album cover'))}" loading="lazy">
                   <span class="cover-play">▶</span>
               </div>`
            : `<img class="track-cover" src="${attr(track.cover_url)}" alt="${attr(i18n('feedback.album_cover', 'Album cover'))}" loading="lazy">`)
        : '';
    const noPreviewHtml = !track.track_id ? `<span class="track-no-preview">${esc(i18n('feedback.no_preview', 'No preview'))}</span>` : '';
    const spotifyLinks = [
        track.spotify_url ? `<a class="track-link" href="${attr(track.spotify_url)}" target="_blank" rel="noopener" title="${attr(i18n('feedback.open_track', 'Open track on Spotify'))}">🎵</a>` : '',
        track.artist_url ? `<a class="track-link" href="${attr(track.artist_url)}" target="_blank" rel="noopener" title="${attr(i18n('feedback.open_artist', 'Open artist on Spotify'))}">🎤</a>` : '',
        track.album_url ? `<a class="track-link" href="${attr(track.album_url)}" target="_blank" rel="noopener" title="${attr(i18n('feedback.open_album', 'Open album on Spotify'))}">💿</a>` : '',
    ].join('');

    return `
        <div class="track-header">
            ${coverHtml}
            <div class="track-info">
                <div class="track-name">${esc(track.artist)} — ${esc(track.track)}${spotifyLinks ? `<span class="track-links">${spotifyLinks}</span>` : ''}</div>
                <div class="track-rationale">${buildRationaleHtml(track.rationale)}</div>
                ${noPreviewHtml}
            </div>
            <div class="track-actions">
                <button class="btn btn-feedback" onclick="${feedbackFn}(${idx})">💬 ${esc(i18n('feedback.open_panel', 'Feedback'))}</button>
                <button class="btn btn-remove"  onclick="${removeFn}(${idx})" aria-label="${attr(i18n('feedback.delete_from_playlist', 'Delete from playlist'))}" title="${attr(i18n('feedback.delete_from_playlist', 'Delete from playlist'))}">🗑</button>
            </div>
        </div>
        <div class="feedback-form" id="${formId}">
            <div class="form-row">
                <label for="${artistId}">${esc(i18n('feedback.artist_label', 'Artist'))}</label>
                <input id="${artistId}" type="text" value="${attr(track.artist)}">
            </div>
            <div class="form-row">
                <label for="${titleId}">${esc(i18n('feedback.track_label', 'Track'))}</label>
                <input id="${titleId}" type="text" value="${attr(track.track)}">
                <div class="form-hint">${esc(i18n('feedback.form_hint', 'Leave empty to apply feedback to the artist in general.'))}</div>
            </div>
            <div class="form-row">
                <label for="${reasonId}">${esc(i18n('feedback.reason_label', 'Reason (optional)'))}</label>
                <input id="${reasonId}" type="text" placeholder="${attr(i18n('feedback.reason_placeholder', 'e.g. perfect energy, boring melody…'))}">
            </div>
            <div class="form-actions form-actions-dual">
                <button class="btn btn-submit-like" id="${submitBtnId}-like" onclick="${submitFn}(${idx},'like')">👍 ${esc(i18n('feedback.submit_like', 'Like'))}</button>
                <button class="btn btn-submit-dislike" id="${submitBtnId}-dislike" onclick="${submitFn}(${idx},'dislike')">👎 ${esc(i18n('feedback.submit_dislike', 'Dislike'))}</button>
                <button class="btn btn-cancel" onclick="${closeFn}(${idx})">${esc(i18n('btn.cancel', 'Cancel'))}</button>
            </div>
        </div>`;
}

export function toggleFeedback(idx) {
    if (State.openFormIndex !== null && State.openFormIndex !== idx) {
        closeFeedback(State.openFormIndex);
    }

    const form = el(`form-${idx}`);
    if (!form) return;
    const isOpen = form.classList.contains('open');

    if (isOpen) {
        closeFeedback(idx);
        return;
    }

    form.classList.add('open');
    State.setOpenFormIndex(idx);
    State.setOpenFormAction(null);
}

export function closeFeedback(idx) {
    const form = el(`form-${idx}`);
    if (form) form.classList.remove('open');
    if (State.openFormIndex === idx) {
        State.setOpenFormIndex(null);
        State.setOpenFormAction(null);
    }
}

export async function submitFeedback(idx, action) {
    action = action || State.openFormAction || 'like';
    const artist = el(`artist-${idx}`).value.trim();
    const track  = el(`title-${idx}`).value.trim();
    const reason = el(`reason-${idx}`).value.trim();

    if (!artist) { showAlert(i18n('feedback.artist_required', 'Artist is required.')); return; }

    // Item 6 (2026-04): artist-level dislike (no track) → confirm, then
    // call the dedicated endpoint that also strips the active playlist.
    if (action === 'dislike' && !track) {
        const msg = i18n(
            'feedback.confirm_dislike_artist',
            'Remove ALL songs by "{artist}" from this playlist and never suggest them again?'
        ).replace('{artist}', artist);
        if (!window.confirm(msg)) {
            return;
        }
        const submitBtnLikeC = el(`submitBtn-${idx}-like`);
        const submitBtnDislikeC = el(`submitBtn-${idx}-dislike`);
        if (submitBtnLikeC) submitBtnLikeC.disabled = true;
        if (submitBtnDislikeC) submitBtnDislikeC.disabled = true;
        try {
            const resp = await fetch('/api/feedback/dislike-artist', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    artist,
                    reason,
                    playlist_id: State.lastGeneratedPlaylistId,
                    source: 'discover',
                }),
            });
            const body = await resp.json().catch(() => ({}));
            if (!resp.ok) {
                showAlert(i18n('msg.error_prefix', 'Error: {detail}').replace('{detail}', body.error || resp.status));
                return;
            }
            const removal = body.removal || {};
            const count = removal.removed_count || 0;
            const toastMsg = count > 0
                ? i18n('feedback.artist_disliked_purged', '👎 Excluded {artist} — removed {count} tracks from playlist.')
                    .replace('{artist}', artist).replace('{count}', count)
                : i18n('feedback.artist_disliked_no_tracks', '👎 Excluded {artist}. (No tracks were on the playlist.)')
                    .replace('{artist}', artist);
            showToast(toastMsg);
            resetDashboard();
            if (typeof window.refreshGettingStarted === 'function') {
                window.refreshGettingStarted();
            }
            // Remove every track in the visible list that matches this artist —
            // not just the one whose form was submitted.
            const removed = removeDiscoverTracksByArtist(artist);
            if (removed === 0) {
                animateRemove(idx);
            }
        } catch (e) {
            showAlert(i18n('msg.network_error', 'Network error: {detail}').replace('{detail}', e.message));
        } finally {
            if (submitBtnLikeC) submitBtnLikeC.disabled = false;
            if (submitBtnDislikeC) submitBtnDislikeC.disabled = false;
        }
        return;
    }

    const submitBtnLike = el(`submitBtn-${idx}-like`);
    const submitBtnDislike = el(`submitBtn-${idx}-dislike`);
    if (submitBtnLike) submitBtnLike.disabled = true;
    if (submitBtnDislike) submitBtnDislike.disabled = true;

    try {
        const srcTrack = State.suggestions[idx];
        const result = await postFeedback({
            action,
            artist,
            track,
            reason,
            playlistId: State.lastGeneratedPlaylistId,
            trackId: srcTrack && srcTrack.track_id,
            source: 'discover',
        });

        if (!result.ok) {
            showAlert(i18n('msg.error_prefix', 'Error: {detail}').replace('{detail}', result.error));
            return;
        }

        const data = result.body;
        const trackLabel = track ? ` — ${track}` : '';

        if (action === 'dislike') {
            const removed = data.removal && data.removal.removed;
            const msg = removed
                ? i18n('feedback.disliked_removed_playlist', '👎 Disliked & removed from playlist: {track}').replace('{track}', `${artist}${trackLabel}`)
                : i18n('feedback.disliked', '👎 Disliked: {track}').replace('{track}', `${artist}${trackLabel}`);
            showToast(msg);

            // Wave 3: Dislike counter → tip trigger
            window._svSessionDislikes = (window._svSessionDislikes || 0) + 1;
            if (window._svSessionDislikes >= 2 && window.Tips) {
                window.Tips.maybeTrigger('disliked_2_plus');
            }
            // Remove disliked track from the ephemeral list
            animateRemove(idx);
        } else {
            showToast(i18n('feedback.liked', '👍 Liked: {track}').replace('{track}', `${artist}${trackLabel}`));
            // Bug-1 fix (2026-05-30): liked tracks stay in the list AND get
            // a green-glow marker so the user can see what they liked and
            // still apply it to a playlist.
            State.markSuggestionLiked(idx);
            const node = el(`track-${idx}`);
            if (node) node.classList.add('liked');
            closeFeedback(idx);
        }

        resetDashboard();

        if (typeof window.refreshGettingStarted === 'function') {
            window.refreshGettingStarted();
        }
    } catch (e) {
        showAlert(i18n('msg.network_error', 'Network error: {detail}').replace('{detail}', e.message));
    } finally {
        if (submitBtnLike) submitBtnLike.disabled = false;
        if (submitBtnDislike) submitBtnDislike.disabled = false;
    }
}

export async function removeTrack(idx) {
    const track = State.suggestions[idx];
    if (!track) { animateRemove(idx); return; }

    try {
        await postRemove({
            artist: track.artist,
            track: track.track,
            playlistId: State.lastGeneratedPlaylistId,
            trackId: track.track_id,
            source: 'discover',
        });
    } catch (e) {
        /* Network error — still remove from UI */
    }

    animateRemove(idx);
}

/**
 * Bug-3 fix (2026-05-30): remove EVERY track by the given artist from the
 * Discover list. Used by both the Discover feedback form and the preview
 * overlay so that "dislike a whole band" always clears the band's other
 * songs — keeping them made no sense once the band is excluded.
 * Iterates descending so splicing doesn't shift indices we still read.
 * Returns the number of cards removed.
 */
export function removeDiscoverTracksByArtist(artist) {
    const target = (artist || '').trim().toLowerCase();
    if (!target) return 0;
    const matchedIdx = [];
    for (let i = 0; i < State.suggestions.length; i++) {
        const t = State.suggestions[i];
        if (!t) continue;
        if ((t.artist || '').trim().toLowerCase() === target) {
            matchedIdx.push(i);
        }
    }
    for (let i = matchedIdx.length - 1; i >= 0; i--) {
        animateRemove(matchedIdx[i]);
    }
    return matchedIdx.length;
}

export function animateRemove(idx) {
    const node = el(`track-${idx}`);
    if (!node) return;
    // CF-Bug-6: notify the preview module BEFORE the splice so it can stop
    // playback / shift its index based on pre-splice positions.
    onExternalTrackRemoved(idx, 'discover');
    node.style.opacity = '0';
    node.style.transform = 'translateX(40px)';
    setTimeout(() => node.remove(), 300);

    State.spliceSuggestion(idx);

    if (State.openFormIndex === idx) {
        State.setOpenFormIndex(null);
        State.setOpenFormAction(null);
    }
}
