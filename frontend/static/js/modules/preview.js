import * as State from './state.js';
import { showAlert } from './ui.js';
import { i18n } from './i18n.js';
import { el } from './dom.js';
import * as Sdk from './spotify-sdk.js';

let currentPreviewIndex = -1;
let currentPreviewSource = 'discover'; // 'discover' or 'review'

const AUTOPLAY_KEY = 'spv_preview_autoplay';

/* ── Web Playback SDK state (§8a) ─────────────────────────────────
 * `_playbackMode` is 'sdk' once we've successfully connected on a
 * Premium account in a runtime with EME/Widevine; 'iframe' otherwise.
 * `_sessionInfo` caches /api/session so we only hit it once per page.
 */
let _playbackMode = 'iframe';
let _sessionInfo = null;
let _sdkInitPromise = null;
let _sdkLastPositionMs = 0;
let _sdkLastDurationMs = 0;
let _sdkScrubberDragging = false;

export function isAutoplayEnabled() {
    const v = localStorage.getItem(AUTOPLAY_KEY);
    return v === null ? true : v === '1';
}

function setAutoplayEnabled(enabled) {
    localStorage.setItem(AUTOPLAY_KEY, enabled ? '1' : '0');
}

function embedUrl(trackId, autoplay = false) {
    // Cache-bust so the embed re-evaluates the user's Spotify login state
    // (without this, a stale anonymous session persists until a hard reload)
    let url = `https://open.spotify.com/embed/track/${encodeURIComponent(trackId)}?utm_source=generator&theme=0&_cb=${Date.now()}`;
    if (autoplay) url += '&autoplay=1';
    return url;
}

/**
 * Replace the iframe DOM element with a fresh one so the browser
 * treats it as a new navigation — required for autoplay to work.
 */
function replaceIframe(src) {
    const old = el('spotifyPreviewIframe');
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
    const prevBtn = el('previewPrev');
    const nextBtn = el('previewNext');
    const counter = el('previewCounter');
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

    if (_playbackMode === 'sdk') {
        sdkPlayCurrentTrack(track).catch(() => fallbackToIframe(track.track_id));
    } else {
        replaceIframe(embedUrl(track.track_id, isAutoplayEnabled()));
    }

    const titleEl = el('spotifyPreviewTitle');
    if (titleEl) titleEl.textContent = `${track.artist} — ${track.track}`;
    updateSdkMeta(track);

    updateNavState();
}

export function openPreviewOverlay(trackId, title, source = 'discover') {
    const overlay = el('spotifyPreviewOverlay');
    if (!overlay || !trackId) return;

    currentPreviewSource = source;
    const tracks = getSourceTracks();
    currentPreviewIndex = tracks.findIndex(t => t && t.track_id === trackId);
    const track = tracks[currentPreviewIndex];

    syncAutoplayCheckbox();
    const titleEl = el('spotifyPreviewTitle');
    if (titleEl && title) titleEl.textContent = title;
    overlay.classList.add('visible');
    updateNavState();
    initSwipeListeners(overlay);

    // Default immediately to iframe so the user sees something while we
    // decide whether the SDK path is available.
    showIframePanel();
    replaceIframe(embedUrl(trackId, isAutoplayEnabled()));

    // Attempt SDK upgrade in the background; swap in on success.
    maybeInitSdk().then((ok) => {
        if (ok && track) {
            showSdkPanel();
            updateSdkMeta(track);
            sdkPlayCurrentTrack(track).catch(() => fallbackToIframe(trackId));
        }
    }).catch(() => { /* already in iframe mode */ });
}

export function closePreviewOverlay() {
    const overlay = el('spotifyPreviewOverlay');
    if (!overlay) return;
    overlay.classList.remove('visible');
    const iframe = el('spotifyPreviewIframe');
    if (iframe) iframe.src = '';
    currentPreviewIndex = -1;
    // Pause any SDK playback so audio doesn't continue after close.
    if (_playbackMode === 'sdk') {
        Sdk.getPlayer()?.pause().catch(() => {});
    }
    closePreviewFeedback();
}

/* ── SDK wiring ──────────────────────────────────────────────────── */

async function fetchSessionInfo() {
    if (_sessionInfo) return _sessionInfo;
    try {
        const res = await fetch('/api/session', { credentials: 'same-origin' });
        if (!res.ok) throw new Error('session_fetch_failed');
        _sessionInfo = await res.json();
    } catch (_) {
        _sessionInfo = { is_premium: false, authenticated: false };
    }
    return _sessionInfo;
}

/** Connect the SDK once per page. Returns true if SDK playback is usable. */
function maybeInitSdk() {
    if (_sdkInitPromise) return _sdkInitPromise;
    _sdkInitPromise = (async () => {
        const info = await fetchSessionInfo();
        if (!info.is_premium) return false;
        try {
            await Sdk.connect({ name: 'SpotyVibe' });
            wireSdkEvents();
            await Sdk.ensureReady();
            _playbackMode = 'sdk';
            return true;
        } catch (e) {
            const { showToast } = await import('./ui.js');
            showToast(i18n('preview.sdk_unavailable', 'Full-track playback unavailable on this device — preview only'));
            return false;
        }
    })();
    return _sdkInitPromise;
}

function wireSdkEvents() {
    Sdk.on('state_changed', onSdkStateChanged);
    ['initialization_error', 'authentication_error', 'account_error'].forEach((evt) => {
        Sdk.on(evt, () => {
            const track = getCurrentPreviewTrack();
            fallbackToIframe(track?.track_id);
        });
    });

    // Wire scrubber drag once.
    const seek = el('sdkPlayerSeek');
    if (seek && !seek.dataset.wired) {
        seek.dataset.wired = '1';
        seek.addEventListener('input', () => { _sdkScrubberDragging = true; });
        seek.addEventListener('change', () => {
            const pct = Number(seek.value) / 100;
            if (_sdkLastDurationMs > 0) {
                Sdk.seek(Math.floor(pct * _sdkLastDurationMs)).catch(() => {});
            }
            _sdkScrubberDragging = false;
        });
    }
}

function onSdkStateChanged(state) {
    if (!state) return;
    _sdkLastPositionMs = state.position || 0;
    _sdkLastDurationMs = state.duration || 0;

    const playBtn = el('sdkPlayToggle');
    if (playBtn) playBtn.textContent = state.paused ? '▶' : '⏸';

    if (!_sdkScrubberDragging) {
        const seek = el('sdkPlayerSeek');
        if (seek && _sdkLastDurationMs > 0) {
            seek.value = String(Math.round((_sdkLastPositionMs / _sdkLastDurationMs) * 100));
        }
        const cur = el('sdkPlayerTimeCur');
        const dur = el('sdkPlayerTimeDur');
        if (cur) cur.textContent = formatMs(_sdkLastPositionMs);
        if (dur) dur.textContent = formatMs(_sdkLastDurationMs);
    }

    // Track-end detection: when paused at (or near) duration, advance.
    const atEnd = state.paused &&
                  _sdkLastDurationMs > 0 &&
                  _sdkLastPositionMs >= _sdkLastDurationMs - 500;
    if (atEnd && isAutoplayEnabled()) {
        nextPreview();
    }
}

function formatMs(ms) {
    const total = Math.max(0, Math.floor(ms / 1000));
    const m = Math.floor(total / 60);
    const s = total % 60;
    return `${m}:${String(s).padStart(2, '0')}`;
}

async function sdkPlayCurrentTrack(track) {
    if (!track || !track.track_id) return;
    await Sdk.playTrack(track.track_id);
}

function updateSdkMeta(track) {
    if (!track) return;
    const art = el('sdkPlayerArt');
    const title = el('sdkPlayerTitle');
    const artist = el('sdkPlayerArtist');
    if (title) title.textContent = track.track || '';
    if (artist) artist.textContent = track.artist || '';
    if (art) {
        const url = track.album_art || track.image_url || '';
        art.src = url;
        art.style.visibility = url ? 'visible' : 'hidden';
    }
}

function showSdkPanel() {
    _playbackMode = 'sdk';
    el('sdkPlayer')?.removeAttribute('hidden');
    const slider = el('spotifyPreviewSlider');
    if (slider) slider.style.display = 'none';
}

function showIframePanel() {
    _playbackMode = 'iframe';
    el('sdkPlayer')?.setAttribute('hidden', '');
    const slider = el('spotifyPreviewSlider');
    if (slider) slider.style.display = '';
}

function fallbackToIframe(trackId) {
    showIframePanel();
    if (trackId) replaceIframe(embedUrl(trackId, isAutoplayEnabled()));
}

export function sdkTogglePlay() {
    Sdk.togglePlay().catch(() => {});
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
    const actions = el('previewInlineActions');
    if (actions) actions.style.display = currentPreviewIndex >= 0 ? 'flex' : 'none';
}

function getCurrentPreviewTrack() {
    const tracks = getSourceTracks();
    return currentPreviewIndex >= 0 ? tracks[currentPreviewIndex] : null;
}

function clearActiveTab() {
    el('previewTabLike')?.classList.remove('active');
    el('previewTabDislike')?.classList.remove('active');
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

    const panel = el('previewFeedbackPanel');
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
    el(tabId)?.classList.add('active');

    // Action-specific colouring on the panel
    panel.classList.remove('action-like', 'action-dislike');
    panel.classList.add('visible', `action-${action}`);
    panel.dataset.action = action;

    const artistInput = el('previewFbArtist');
    const trackInput = el('previewFbTrack');
    const reasonInput = el('previewFbReason');
    const submitBtn = el('previewFbSubmit');

    if (artistInput) artistInput.value = track.artist || '';
    if (trackInput) trackInput.value = track.track || '';
    if (reasonInput) reasonInput.value = '';

    if (action === 'like') {
        submitBtn.textContent = i18n('btn.submit_like', '👍 Submit');
        submitBtn.className = 'btn btn-submit-like';
    } else {
        submitBtn.textContent = i18n('btn.submit_dislike', '👎 Submit');
        submitBtn.className = 'btn btn-submit-dislike';
    }
}

export function closePreviewFeedback() {
    const panel = el('previewFeedbackPanel');
    if (panel) {
        panel.classList.remove('visible', 'action-like', 'action-dislike');
    }
    clearActiveTab();
    currentFeedbackAction = null;
}

export async function submitPreviewFeedback() {
    const panel = el('previewFeedbackPanel');
    const action = panel ? panel.dataset.action : 'like';
    const artist = el('previewFbArtist').value.trim();
    const track = el('previewFbTrack').value.trim();
    const reason = el('previewFbReason').value.trim();

    if (!artist) { showAlert(i18n('feedback.artist_required', 'Artist is required.')); return; }

    const submitBtn = el('previewFbSubmit');
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
            showAlert(i18n('msg.error_prefix', 'Error: {detail}').replace('{detail}', data.error || 'unknown'));
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
            showToast(i18n('review.disliked_removed', '👎 Disliked & removed: {track}').replace('{track}', `${artist}${trackLabel}`));
        } else {
            showToast(i18n('review.liked', '👍 Liked: {track}').replace('{track}', `${artist}${trackLabel}`));
        }

        // Remove track from source list and advance preview
        removeCurrentAndAdvance();
    } catch (e) {
        showAlert(i18n('msg.network_error', 'Network error: {detail}').replace('{detail}', e.message));
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
        showToast(i18n('feedback.removed_from_playlist', 'Removed from playlist: {track}').replace('{track}', `${track.artist} — ${track.track}`));
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
        const node = el(`review-track-${idx}`);
        if (node) { node.style.opacity = '0'; node.style.transform = 'translateX(40px)'; setTimeout(() => node.remove(), 300); }
        State.spliceReviewTrack(idx);
    } else {
        const node = el(`track-${idx}`);
        if (node) { node.style.opacity = '0'; node.style.transform = 'translateX(40px)'; setTimeout(() => node.remove(), 300); }
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

/* ── Touch swipe support for mobile preview ─────────────────────────── */
let _swipeInitialized = false;
let _swipeStartX = 0;
let _swipeStartY = 0;

function initSwipeListeners(overlay) {
    if (_swipeInitialized) return;
    _swipeInitialized = true;

    const panel = overlay.querySelector('.spotify-preview-panel');
    if (!panel) return;

    panel.addEventListener('touchstart', (e) => {
        _swipeStartX = e.touches[0].clientX;
        _swipeStartY = e.touches[0].clientY;
    }, { passive: true });

    panel.addEventListener('touchend', (e) => {
        const dx = e.changedTouches[0].clientX - _swipeStartX;
        const dy = e.changedTouches[0].clientY - _swipeStartY;
        const MIN_SWIPE = 60;

        // Only act on horizontal swipes (ignore vertical scrolling)
        if (Math.abs(dx) > MIN_SWIPE && Math.abs(dx) > Math.abs(dy) * 1.5) {
            if (dx < 0) nextPreview();   // swipe left → next
            else        prevPreview();   // swipe right → previous
        }
    }, { passive: true });
}

function syncAutoplayCheckbox() {
    const cb = el('previewAutoplayToggle');
    if (cb) cb.checked = isAutoplayEnabled();
}

export function togglePreviewAutoplay(ev) {
    setAutoplayEnabled(!!ev?.target?.checked);
}
