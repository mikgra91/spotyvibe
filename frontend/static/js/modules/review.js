import * as State from './state.js';
import { buildTrackCardHtml } from './feedback.js';
import { showToast, showAlert, showConfirm } from './ui.js';
import { i18n } from './i18n.js';
import { refreshDiscoverPlaylistPicker } from './playlist-mode.js';
import { resetDashboard } from './taste_dashboard.js';
import { el } from './dom.js';

export function toggleReviewBody() {
    const body = el('reviewBody');
    const btn = el('reviewToggleBtn');
    const isHidden = body.classList.toggle('hidden');
    const expanded = (!isHidden).toString();
    if (btn) {
        btn.textContent = isHidden ? i18n('btn.show', 'Show') : i18n('btn.hide', 'Hide');
        btn.setAttribute('aria-expanded', expanded);
    }
    const header = document.querySelector('#reviewSection > .train-header');
    if (header) header.setAttribute('aria-expanded', expanded);

    // Lazy-load playlists on first expand
    if (!isHidden && !body.dataset.loaded) {
        body.dataset.loaded = '1';
        populateReviewPlaylistPicker();
    }
}

/**
 * Load tracks from a selected playlist and render them in the review list.
 */
export async function loadPlaylistTracks() {
    const picker = el('reviewPlaylistPicker');
    if (!picker || !picker.value) {
        showToast(i18n('review.select_playlist_first', 'Please select a playlist first.'));
        return;
    }
    const playlistId = picker.value;
    const listEl = el('reviewTrackList');
    const counterEl = el('reviewTrackCounter');
    const loadArea = el('reviewLoadingArea');
    const loadBtn = el('reviewLoadBtn');

    // Show inline loading spinner
    if (loadArea) loadArea.classList.remove('hidden');
    if (loadBtn) { loadBtn.disabled = true; loadBtn.textContent = i18n('msg.loading', '⏳ Loading…'); }
    listEl.innerHTML = '';

    try {
        const resp = await fetch(`/api/playlist/${encodeURIComponent(playlistId)}/tracks`);
        const data = await resp.json();
        if (data.error) {
            listEl.innerHTML = `<p style="color:var(--error)">${data.error}</p>`;
            return;
        }
        const tracks = data.tracks || [];
        State.setReviewTracks(tracks);
        if (counterEl) counterEl.textContent = i18n('review.track_count', '{count} track(s)').replace('{count}', tracks.length);
        renderReviewTracks();
    } catch (e) {
        listEl.innerHTML = `<p style="color:var(--error)">${i18n('review.load_failed', 'Failed to load playlist tracks.')}</p>`;
    } finally {
        if (loadArea) loadArea.classList.add('hidden');
        if (loadBtn) { loadBtn.disabled = false; loadBtn.textContent = '🔄 ' + i18n('btn.load_playlist', 'Load Playlist'); }
    }
}

export function renderReviewTracks() {
    const list = el('reviewTrackList');
    const trackArea = el('reviewTrackArea');
    list.innerHTML = '';
    const tracks = State.reviewTracks;

    if (!tracks || tracks.filter(Boolean).length === 0) {
        list.innerHTML = `<p style="color:var(--text-muted)">${i18n('review.no_tracks', 'No tracks loaded.')}</p>`;
        if (trackArea) trackArea.classList.add('hidden');
        return;
    }

    if (trackArea) trackArea.classList.remove('hidden');

    tracks.forEach((track, idx) => {
        if (!track) return;
        const li = document.createElement('li');
        li.className = 'track-item';
        li.id = `review-track-${idx}`;
        li.innerHTML = buildTrackCardHtml(track, idx, 'review');
        list.appendChild(li);
    });
}

/* ── Review-specific feedback functions ── */

export function toggleReviewFeedback(idx, action) {
    const form = el(`review-form-${idx}`);
    if (!form) return;
    const isOpen = form.classList.contains('open');

    // Close any other open review form
    document.querySelectorAll('#reviewTrackList .feedback-form.open').forEach(f => {
        if (f.id !== `review-form-${idx}`) f.classList.remove('open');
    });

    if (isOpen && form.dataset.action === action) {
        form.classList.remove('open');
        return;
    }

    form.classList.add('open');
    form.dataset.action = action;

    const submitBtn = el(`review-submitBtn-${idx}`);
    if (action === 'like') {
        submitBtn.textContent = i18n('btn.submit_like', '👍 Submit');
        submitBtn.className = 'btn btn-submit-like';
    } else {
        submitBtn.textContent = i18n('btn.submit_dislike', '👎 Submit');
        submitBtn.className = 'btn btn-submit-dislike';
    }
}

export function closeReviewFeedback(idx) {
    const form = el(`review-form-${idx}`);
    if (form) form.classList.remove('open');
}

export async function submitReviewFeedback(idx) {
    const artist = el(`review-artist-${idx}`).value.trim();
    const track  = el(`review-title-${idx}`).value.trim();
    const reason = el(`review-reason-${idx}`).value.trim();
    const form = el(`review-form-${idx}`);
    const action = form ? form.dataset.action : 'like';

    if (!artist) { showAlert(i18n('feedback.artist_required', 'Artist is required.')); return; }

    const submitBtn = el(`review-submitBtn-${idx}`);
    submitBtn.disabled = true;
    submitBtn.textContent = '…';

    try {
        const resp = await fetch('/api/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action,
                artist,
                track: track || null,
                reason: reason || null,
            }),
        });

        if (!resp.ok) {
            const data = await resp.json();
            showAlert(i18n('msg.error_prefix', 'Error: {detail}').replace('{detail}', data.error || 'unknown'));
            return;
        }

        const trackLabel = track ? ` — ${track}` : '';

        if (action === 'dislike') {
            // Dislike: record feedback + remove from Spotify playlist
            const reviewTrack = State.reviewTracks[idx];
            if (reviewTrack) {
                await fetch('/api/remove', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ artist: reviewTrack.artist, track: reviewTrack.track }),
                }).catch(() => {});
            }
            showToast(i18n('review.disliked_removed', '👎 Disliked & removed: {track}').replace('{track}', `${artist}${trackLabel}`));
        } else {
            showToast(i18n('review.liked', '👍 Liked: {track}').replace('{track}', `${artist}${trackLabel}`));
        }

        resetDashboard();

        animateReviewRemove(idx);
    } catch (e) {
        showAlert(i18n('msg.network_error', 'Network error: {detail}').replace('{detail}', e.message));
    } finally {
        submitBtn.disabled = false;
    }
}

/**
 * Dismiss: remove from Spotify playlist without recording profile feedback.
 */
export async function dismissReviewTrack(idx) {
    const track = State.reviewTracks[idx];
    if (!track) { animateReviewRemove(idx); return; }

    try {
        const resp = await fetch('/api/remove', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ artist: track.artist, track: track.track }),
        });
        const data = await resp.json();
        const msg = data.removed
            ? i18n('feedback.removed_from_playlist', 'Removed from playlist: {track}').replace('{track}', `${track.artist} — ${track.track}`)
            : i18n('feedback.removed', 'Removed: {track}').replace('{track}', `${track.artist} — ${track.track}`);
        showToast(msg);
    } catch (e) {
        /* Network error — still remove from UI */
    }

    animateReviewRemove(idx);
}

function animateReviewRemove(idx) {
    const el = el(`review-track-${idx}`);
    if (!el) return;
    el.style.opacity = '0';
    el.style.transform = 'translateX(40px)';
    setTimeout(() => el.remove(), 300);

    State.spliceReviewTrack(idx);
    // Track count changed — refresh both playlist pickers
    refreshDiscoverPlaylistPicker().then(() => populateReviewPlaylistPicker());
}

/**
 * Populate the review playlist picker dropdown.
 * Shares data with the Discover section picker via State.cachedPlaylists.
 */
export async function populateReviewPlaylistPicker() {
    const picker = el('reviewPlaylistPicker');
    if (!picker) return;

    let playlists = State.cachedPlaylists;
    if (!playlists) {
        try {
            const resp = await fetch('/api/playlists');
            const data = await resp.json();
            playlists = data.playlists || [];
            State.setCachedPlaylists(playlists);
        } catch {
        picker.innerHTML = `<option value="">${i18n('review.playlists_load_failed', 'Failed to load playlists')}</option>`;
        return;
        }
    }

    picker.innerHTML = `<option value="">${i18n('review.select_placeholder', 'Select a playlist…')}</option>` +
        playlists.map(pl =>
            `<option value="${esc(pl.id)}">${esc(pl.name)}</option>`
        ).join('');
}

export async function refreshReviewPlaylistPicker() {
    State.invalidateCachedPlaylists();
    await populateReviewPlaylistPicker();
}

export async function deleteSelectedPlaylist(pickerId) {
    const picker = el(pickerId);
    if (!picker || !picker.value) {
        showToast(i18n('review.select_playlist_first', 'Please select a playlist first.'), 'error');
        return;
    }
    const playlistId = picker.value;
    const playlistName = picker.options[picker.selectedIndex]?.text || playlistId;

    const ok = await showConfirm(
        i18n('playlist.delete_confirm', 'Delete playlist "{name}"?\n\nThis cannot be undone.')
            .replace('{name}', playlistName)
    );
    if (!ok) return;

    try {
        const resp = await fetch(`/api/playlist/${encodeURIComponent(playlistId)}`, { method: 'DELETE' });
        const data = await resp.json();
        if (!resp.ok || data.error) {
            showToast(data.error || i18n('playlist.delete_failed', 'Failed to delete playlist.'), 'error');
            return;
        }
        showToast(i18n('playlist.deleted', 'Playlist deleted.'), 'success');
        // Refresh both pickers
        State.invalidateCachedPlaylists();
        await populateReviewPlaylistPicker();
        await refreshDiscoverPlaylistPicker();
    } catch (e) {
        showToast(i18n('msg.network_error', 'Network error: {detail}').replace('{detail}', e.message), 'error');
    }
}
