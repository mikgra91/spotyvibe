import * as State from './state.js';
import { buildTrackCardHtml } from './feedback.js';
import { showToast } from './ui.js';
import { refreshDiscoverPlaylistPicker } from './playlist-mode.js';

export function toggleReviewBody() {
    const body = document.getElementById('reviewBody');
    const btn = document.getElementById('reviewToggleBtn');
    const isHidden = body.classList.toggle('hidden');
    const expanded = (!isHidden).toString();
    if (btn) {
        btn.textContent = isHidden ? 'Show' : 'Hide';
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
    const picker = document.getElementById('reviewPlaylistPicker');
    if (!picker || !picker.value) {
        showToast('Please select a playlist first.');
        return;
    }
    const playlistId = picker.value;
    const listEl = document.getElementById('reviewTrackList');
    const counterEl = document.getElementById('reviewTrackCounter');
    const loadArea = document.getElementById('reviewLoadingArea');
    const loadBtn = document.getElementById('reviewLoadBtn');

    // Show inline loading spinner
    if (loadArea) loadArea.classList.remove('hidden');
    if (loadBtn) { loadBtn.disabled = true; loadBtn.textContent = '⏳ Loading…'; }
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
        if (counterEl) counterEl.textContent = `${tracks.length} track(s)`;
        renderReviewTracks();
    } catch (e) {
        listEl.innerHTML = '<p style="color:var(--error)">Failed to load playlist tracks.</p>';
    } finally {
        if (loadArea) loadArea.classList.add('hidden');
        if (loadBtn) { loadBtn.disabled = false; loadBtn.textContent = '🔄 Load Playlist'; }
    }
}

export function renderReviewTracks() {
    const list = document.getElementById('reviewTrackList');
    const trackArea = document.getElementById('reviewTrackArea');
    list.innerHTML = '';
    const tracks = State.reviewTracks;

    if (!tracks || tracks.filter(Boolean).length === 0) {
        list.innerHTML = '<p style="color:var(--text-muted)">No tracks loaded.</p>';
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
    const form = document.getElementById(`review-form-${idx}`);
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

    const submitBtn = document.getElementById(`review-submitBtn-${idx}`);
    if (action === 'like') {
        submitBtn.textContent = '👍 Submit';
        submitBtn.className = 'btn btn-submit-like';
    } else {
        submitBtn.textContent = '👎 Submit';
        submitBtn.className = 'btn btn-submit-dislike';
    }
}

export function closeReviewFeedback(idx) {
    const form = document.getElementById(`review-form-${idx}`);
    if (form) form.classList.remove('open');
}

export async function submitReviewFeedback(idx) {
    const artist = document.getElementById(`review-artist-${idx}`).value.trim();
    const track  = document.getElementById(`review-title-${idx}`).value.trim();
    const reason = document.getElementById(`review-reason-${idx}`).value.trim();
    const form = document.getElementById(`review-form-${idx}`);
    const action = form ? form.dataset.action : 'like';

    if (!artist) { alert('Artist is required.'); return; }

    const submitBtn = document.getElementById(`review-submitBtn-${idx}`);
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
            alert('Error: ' + (data.error || 'unknown'));
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
            showToast(`👎 Disliked & removed: ${artist}${trackLabel}`);
        } else {
            showToast(`👍 Liked: ${artist}${trackLabel}`);
        }

        animateReviewRemove(idx);
    } catch (e) {
        alert('Network error: ' + e.message);
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
            ? `Removed from playlist: ${track.artist} — ${track.track}`
            : `Removed: ${track.artist} — ${track.track}`;
        showToast(msg);
    } catch (e) {
        /* Network error — still remove from UI */
    }

    animateReviewRemove(idx);
}

function animateReviewRemove(idx) {
    const el = document.getElementById(`review-track-${idx}`);
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
    const picker = document.getElementById('reviewPlaylistPicker');
    if (!picker) return;

    let playlists = State.cachedPlaylists;
    if (!playlists) {
        try {
            const resp = await fetch('/api/playlists');
            const data = await resp.json();
            playlists = data.playlists || [];
            State.setCachedPlaylists(playlists);
        } catch {
            picker.innerHTML = '<option value="">Failed to load playlists</option>';
            return;
        }
    }

    picker.innerHTML = '<option value="">Select a playlist…</option>' +
        playlists.map(pl =>
            `<option value="${pl.id}">${pl.name} (${pl.track_count} tracks)</option>`
        ).join('');
}

