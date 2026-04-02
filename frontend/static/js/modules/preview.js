import * as State from './state.js';

let currentPreviewIndex = -1;
let currentPreviewSource = 'discover'; // 'discover' or 'review'

function embedUrl(trackId, autoplay = false) {
    let url = `https://open.spotify.com/embed/track/${encodeURIComponent(trackId)}?utm_source=generator&theme=0`;
    if (autoplay) url += '&autoplay=1';
    return url;
}

/**
 * Replace the iframe DOM element with a fresh one so the browser
 * treats it as a new navigation — required for autoplay to work.
 */
function replaceIframe(src) {
    const old = document.getElementById('spotifyPreviewIframe');
    if (!old) return;
    const fresh = document.createElement('iframe');
    fresh.id = 'spotifyPreviewIframe';
    fresh.width = '100%';
    fresh.height = '190';
    fresh.frameBorder = '0';
    fresh.allowFullscreen = true;
    fresh.allow = 'autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture';
    fresh.loading = 'lazy';
    fresh.src = src;
    old.replaceWith(fresh);
}

/** Get the track list for the current preview source. */
function getSourceTracks() {
    return currentPreviewSource === 'review' ? State.reviewTracks : State.suggestions;
}

function updateNavState() {
    const prevBtn = document.getElementById('previewPrev');
    const nextBtn = document.getElementById('previewNext');
    const counter = document.getElementById('previewCounter');
    const tracks = getPreviewableTracks();
    const pos = tracks.findIndex(t => t._origIdx === currentPreviewIndex);

    if (prevBtn) prevBtn.disabled = pos <= 0;
    if (nextBtn) nextBtn.disabled = pos < 0 || pos >= tracks.length - 1;
    if (counter) {
        counter.textContent = tracks.length > 1 ? `${pos + 1} / ${tracks.length}` : '';
    }

    // Update inline feedback buttons visibility
    updatePreviewFeedbackState();
}

/** Returns only tracks that have a track_id (previewable). Preserves original index. */
function getPreviewableTracks() {
    return getSourceTracks()
        .map((t, i) => t ? { ...t, _origIdx: i } : null)
        .filter(t => t && t.track_id);
}

function loadTrackByIndex(idx) {
    const tracks = getSourceTracks();
    const track = tracks[idx];
    if (!track || !track.track_id) return;
    currentPreviewIndex = idx;

    replaceIframe(embedUrl(track.track_id, true));

    const titleEl = document.getElementById('spotifyPreviewTitle');
    if (titleEl) titleEl.textContent = `${track.artist} — ${track.track}`;

    updateNavState();
}

export function openPreviewOverlay(trackId, title, source = 'discover') {
    const overlay = document.getElementById('spotifyPreviewOverlay');
    if (!overlay || !trackId) return;

    currentPreviewSource = source;
    const tracks = getSourceTracks();

    // Determine the index in the source track list
    currentPreviewIndex = tracks.findIndex(t => t && t.track_id === trackId);

    // Fresh iframe for autoplay to work reliably
    replaceIframe(embedUrl(trackId, true));
    const titleEl = document.getElementById('spotifyPreviewTitle');
    if (titleEl && title) titleEl.textContent = title;
    overlay.classList.add('visible');
    updateNavState();
}

export function closePreviewOverlay() {
    const overlay = document.getElementById('spotifyPreviewOverlay');
    if (!overlay) return;
    overlay.classList.remove('visible');
    const iframe = document.getElementById('spotifyPreviewIframe');
    if (iframe) iframe.src = '';
    currentPreviewIndex = -1;
    // Reset feedback state
    closePreviewFeedback();
}

export function prevPreview() {
    const tracks = getPreviewableTracks();
    const pos = tracks.findIndex(t => t._origIdx === currentPreviewIndex);
    if (pos > 0) loadTrackByIndex(tracks[pos - 1]._origIdx);
}

export function nextPreview() {
    const tracks = getPreviewableTracks();
    const pos = tracks.findIndex(t => t._origIdx === currentPreviewIndex);
    if (pos >= 0 && pos < tracks.length - 1) loadTrackByIndex(tracks[pos + 1]._origIdx);
}

/* ── Inline Preview Feedback ── */

let currentFeedbackAction = null;  // track which tab is open: 'like', 'dislike', or null

function updatePreviewFeedbackState() {
    const actions = document.getElementById('previewInlineActions');
    if (actions) actions.style.display = currentPreviewIndex >= 0 ? 'flex' : 'none';
}

function getCurrentPreviewTrack() {
    const tracks = getSourceTracks();
    return currentPreviewIndex >= 0 ? tracks[currentPreviewIndex] : null;
}

function clearActiveTab() {
    document.getElementById('previewTabLike')?.classList.remove('active');
    document.getElementById('previewTabDislike')?.classList.remove('active');
}

export function previewLike() {
    togglePreviewFeedbackForm('like');
}

export function previewDislike() {
    togglePreviewFeedbackForm('dislike');
}

function togglePreviewFeedbackForm(action) {
    const track = getCurrentPreviewTrack();
    if (!track) return;

    const panel = document.getElementById('previewFeedbackPanel');
    if (!panel) return;

    // Toggle: if same action tab clicked again, close the form
    if (currentFeedbackAction === action && panel.classList.contains('visible')) {
        closePreviewFeedback();
        return;
    }

    // Open (or switch) the feedback form
    currentFeedbackAction = action;

    // Update active tab
    clearActiveTab();
    const tabId = action === 'like' ? 'previewTabLike' : 'previewTabDislike';
    document.getElementById(tabId)?.classList.add('active');

    // Action-specific colouring on the panel
    panel.classList.remove('action-like', 'action-dislike');
    panel.classList.add('visible', `action-${action}`);
    panel.dataset.action = action;

    const artistInput = document.getElementById('previewFbArtist');
    const trackInput = document.getElementById('previewFbTrack');
    const reasonInput = document.getElementById('previewFbReason');
    const submitBtn = document.getElementById('previewFbSubmit');

    if (artistInput) artistInput.value = track.artist || '';
    if (trackInput) trackInput.value = track.track || '';
    if (reasonInput) reasonInput.value = '';

    if (action === 'like') {
        submitBtn.textContent = '👍 Submit Like';
        submitBtn.className = 'btn btn-submit-like';
    } else {
        submitBtn.textContent = '👎 Submit Dislike';
        submitBtn.className = 'btn btn-submit-dislike';
    }
}

export function closePreviewFeedback() {
    const panel = document.getElementById('previewFeedbackPanel');
    if (panel) {
        panel.classList.remove('visible', 'action-like', 'action-dislike');
    }
    clearActiveTab();
    currentFeedbackAction = null;
}

export async function submitPreviewFeedback() {
    const panel = document.getElementById('previewFeedbackPanel');
    const action = panel ? panel.dataset.action : 'like';
    const artist = document.getElementById('previewFbArtist').value.trim();
    const track = document.getElementById('previewFbTrack').value.trim();
    const reason = document.getElementById('previewFbReason').value.trim();

    if (!artist) { alert('Artist is required.'); return; }

    const submitBtn = document.getElementById('previewFbSubmit');
    submitBtn.disabled = true;
    submitBtn.textContent = '…';

    try {
        const resp = await fetch('/api/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action, artist, track: track || null, reason: reason || null }),
        });
        if (!resp.ok) {
            const data = await resp.json();
            alert('Error: ' + (data.error || 'unknown'));
            return;
        }

        const trackLabel = track ? ` — ${track}` : '';
        const { showToast } = await import('./ui.js');

        if (action === 'dislike') {
            // Also remove from Spotify playlist
            const currentTrack = getCurrentPreviewTrack();
            if (currentTrack) {
                await fetch('/api/remove', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ artist: currentTrack.artist, track: currentTrack.track }),
                }).catch(() => {});
            }
            showToast(`👎 Disliked & removed: ${artist}${trackLabel}`);
        } else {
            showToast(`👍 Liked: ${artist}${trackLabel}`);
        }

        // Remove track from source list and advance preview
        removeCurrentAndAdvance();
    } catch (e) {
        alert('Network error: ' + e.message);
    } finally {
        submitBtn.disabled = false;
    }
}

export async function previewDismiss() {
    const track = getCurrentPreviewTrack();
    if (!track) return;

    try {
        await fetch('/api/remove', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ artist: track.artist, track: track.track }),
        });
        const { showToast } = await import('./ui.js');
        showToast(`Removed from playlist: ${track.artist} — ${track.track}`);
    } catch (e) {
        /* still remove from UI */
    }

    removeCurrentAndAdvance();
}

/**
 * Remove the currently previewed track from the source list,
 * animate the card out, update counters, and advance to the next track.
 */
function removeCurrentAndAdvance() {
    closePreviewFeedback();

    const idx = currentPreviewIndex;
    const source = currentPreviewSource;

    // Remove the card from the track list UI
    if (source === 'review') {
        const el = document.getElementById(`review-track-${idx}`);
        if (el) { el.style.opacity = '0'; el.style.transform = 'translateX(40px)'; setTimeout(() => el.remove(), 300); }
        State.spliceReviewTrack(idx);
    } else {
        const el = document.getElementById(`track-${idx}`);
        if (el) { el.style.opacity = '0'; el.style.transform = 'translateX(40px)'; setTimeout(() => el.remove(), 300); }
        State.spliceSuggestion(idx);
    }

    // Advance to next previewable track
    const tracks = getPreviewableTracks();
    if (tracks.length === 0) {
        closePreviewOverlay();
        return;
    }

    // Find the next track after the removed one
    const nextTrack = tracks.find(t => t._origIdx > idx) || tracks[0];
    if (nextTrack) {
        loadTrackByIndex(nextTrack._origIdx);
    } else {
        closePreviewOverlay();
    }
}
