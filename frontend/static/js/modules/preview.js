import * as State from './state.js';
import { showAlert } from './ui.js';
import { i18n } from './i18n.js';
import { el } from './dom.js';
import * as Sdk from './spotify-sdk.js';
import { postFeedback, postRemove } from './feedback-api.js';

let currentPreviewIndex = -1;
let currentPreviewSource = 'discover'; // 'discover' or 'review'

const AUTOPLAY_KEY = 'spv_preview_autoplay';

/* ── Debug logging ──────────────────────────────────────────────────
 * Verbose `[SDK]` / `[feedback]` / `[dismiss]` traces are noise for
 * end users but indispensable when diagnosing Brave/Widevine issues.
 * Gate them behind `window.SV_DEBUG = true` (set from devtools or via
 * the debug-mode setting once we wire it up). Errors that block real
 * user actions still go through console.error directly.
 */
function _dbg(...args) { if (window.SV_DEBUG) console.info(...args); }
function _dbgWarn(...args) { if (window.SV_DEBUG) console.warn(...args); }
function _dbgError(...args) { if (window.SV_DEBUG) console.error(...args); }

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

/* ── SDK position ticker (Items 3 + 5) ─────────────────────────────
 * The Spotify Web Playback SDK only fires `state_changed` on discrete
 * transitions (play/pause/seek/track-change), never continuously. That
 * makes the timebar appear frozen between events (especially when the
 * tab was hidden) and makes track-end detection unreliable because the
 * SDK can reset `position` to 0 the moment a track ends, missing the
 * "position >= duration - 500" window.
 *
 * The ticker below extrapolates the position from the last authoritative
 * SDK state using wall-clock time, redraws the seek bar / time labels
 * 4× per second while playing, and triggers `nextPreview()` once the
 * extrapolated position crosses the duration. Real `state_changed`
 * events still re-anchor `_sdkLastPositionMs` so we never drift.
 */
let _tickerHandle = null;
let _sdkPositionAnchorMs = 0;     // wall-clock time when _sdkLastPositionMs was set
let _sdkPaused = true;
let _sdkAdvanceFiredFor = null;   // track id we already auto-advanced from
let _sdkCurrentTrackId = null;    // id of the SDK's current_track from the last state_changed

/* ── Profile-regen tip counter (Item 4) ─────────────────────────────
 * Trigger the "regenerate profile" tip after 10+ feedback events in a
 * fresh session, then re-trigger every additional 30 events. The tip
 * itself (`tips.js` → `regenerate_profile_after_feedback`) is marked
 * `oncePerSessionOnly`, so it re-appears on the next app launch too.
 */
const _REGEN_TIP_INITIAL_THRESHOLD = 10;
const _REGEN_TIP_REPEAT_INTERVAL = 30;
let _feedbackEventCount = 0;
let _feedbackEventsAtLastTip = -_REGEN_TIP_INITIAL_THRESHOLD;

function _maybeTriggerRegenProfileTip() {
    _feedbackEventCount += 1;
    const since = _feedbackEventCount - _feedbackEventsAtLastTip;
    const initialReady = _feedbackEventsAtLastTip < 0
        && _feedbackEventCount >= _REGEN_TIP_INITIAL_THRESHOLD;
    const repeatReady = _feedbackEventsAtLastTip >= 0
        && since >= _REGEN_TIP_REPEAT_INTERVAL;
    if (!initialReady && !repeatReady) return;
    if (!window.Tips || typeof window.Tips.maybeTrigger !== 'function') return;
    window.Tips.maybeTrigger('regenerate_profile_after_feedback');
    _feedbackEventsAtLastTip = _feedbackEventCount;
}

/* ── SDK failure tracking (Brave/Widevine diagnostic) ───────────────
 * Count repeated SDK-init failures across sessions; once we cross a
 * threshold we trigger a one-time Tips notification pointing the user
 * at the real cause (Widevine disabled — common on Brave).
 */
const SDK_FAIL_COUNT_KEY = 'sv.sdk_fail_count';
const SDK_FAIL_THRESHOLD = 5;

function _getSdkFailureCount() {
    try { return parseInt(localStorage.getItem(SDK_FAIL_COUNT_KEY) || '0', 10) || 0; }
    catch { return 0; }
}

function _resetSdkFailureCount() {
    try { localStorage.removeItem(SDK_FAIL_COUNT_KEY); } catch { /* ignore */ }
}

async function _isBrave() {
    try {
        return !!(navigator.brave && await navigator.brave.isBrave());
    } catch { return false; }
}

async function _recordSdkFailureAndMaybeTip() {
    const count = _getSdkFailureCount() + 1;
    try { localStorage.setItem(SDK_FAIL_COUNT_KEY, String(count)); } catch { /* ignore */ }
    if (count < SDK_FAIL_THRESHOLD) return;
    if (!window.Tips) return;
    const tipId = (await _isBrave()) ? 'sdk_brave_widevine' : 'sdk_no_drm';
    window.Tips.maybeTrigger(tipId);
}

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

    // Show the loader; keep both the SDK panel and iframe fallback hidden
    // until we know which playback path is available. This avoids flashing
    // the embedded player only to swap it out for the SDK moments later.
    showLoader();

    maybeInitSdk().then((ok) => {
        _dbg('[SDK] maybeInitSdk() →', ok, 'track present?', !!track);
        if (ok && track) {
            showSdkPanel();
            updateSdkMeta(track);
            sdkPlayCurrentTrack(track).catch(() => {
                _dbgWarn('[SDK] falling back to iframe after playTrack failure');
                fallbackToIframe(trackId);
            });
        } else {
            fallbackToIframe(trackId);
        }
        setTimeout(maybeShowRateHint, 400);
    }).catch(() => {
        fallbackToIframe(trackId);
    });
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
    _stopTicker();
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
        _dbg('[SDK] session info:', info);
        if (!info.is_premium) {
            _dbgWarn('[SDK] skipping init — not Premium');
            return false;
        }
        try {
            _dbg('[SDK] connect() starting…');
            await Sdk.connect({ name: 'SpotyVibe' });
            _dbg('[SDK] connect() resolved');
            wireSdkEvents();
            _dbg('[SDK] ensureReady() starting…');
            await Sdk.ensureReady();
            _dbg('[SDK] ensureReady() resolved — SDK ready');
            _playbackMode = 'sdk';
            _resetSdkFailureCount();
            return true;
        } catch (e) {
            _dbgError('[SDK] init failed:', e);
            const { showToast } = await import('./ui.js');
            showToast(i18n('preview.sdk_unavailable', 'Full-track playback unavailable on this device — preview only'));
            _recordSdkFailureAndMaybeTip();
            return false;
        }
    })();
    return _sdkInitPromise;
}

function wireSdkEvents() {
    Sdk.on('state_changed', onSdkStateChanged);
    ['initialization_error', 'authentication_error', 'account_error', 'playback_error'].forEach((evt) => {
        Sdk.on(evt, (payload) => {
            _dbgError(`[SDK] ${evt}:`, payload);
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

    // Resync on tab return — the SDK throttles state events while hidden,
    // so the ticker's projection drifts. Re-anchor from authoritative state.
    if (!wireSdkEvents._visibilityWired) {
        wireSdkEvents._visibilityWired = true;
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState !== 'visible') return;
            if (_playbackMode !== 'sdk') return;
            const player = Sdk.getPlayer?.();
            if (!player || typeof player.getCurrentState !== 'function') return;
            player.getCurrentState().then((state) => {
                if (state) onSdkStateChanged(state);
            }).catch(() => { /* ignore */ });
        });
    }
}

function onSdkStateChanged(state) {
    if (!state) return;

    const newPos = state.position || 0;
    const newPaused = !!state.paused;
    const newDuration = state.duration || 0;
    const newTrackId = state.track_window?.current_track?.id || null;

    // ── Natural end-of-track detection (re-opens the bug "fixed" in item 5) ──
    // The Spotify Web Playback SDK fires state_changed with
    //   { paused: true, position: 0, current_track: <same as before> }
    // the instant a track ends naturally. The 250 ms ticker can miss the
    // tiny "projected >= duration - 100" window, so we also detect it here:
    // we WERE playing past the start of THIS track, and now we're paused
    // back at position 0 on the same current_track id → track just finished.
    const sameTrack = newTrackId && newTrackId === _sdkCurrentTrackId;
    const wasPlayingPastStart = !_sdkPaused && _sdkLastPositionMs > 1000;
    const looksLikeNaturalEnd = sameTrack && wasPlayingPastStart
                                && newPaused && newPos === 0;

    _sdkLastPositionMs = newPos;
    _sdkLastDurationMs = newDuration;
    _sdkPositionAnchorMs = performance.now();
    _sdkPaused = newPaused;

    // Reset auto-advance latch when a new track is loaded so the next
    // track-end can also fire.
    if (newTrackId && newTrackId !== _sdkCurrentTrackId) {
        _sdkAdvanceFiredFor = null;
        _sdkCurrentTrackId = newTrackId;
    } else if (newTrackId && _sdkCurrentTrackId === null) {
        _sdkCurrentTrackId = newTrackId;
    }

    const playBtn = el('sdkPlayToggle');
    if (playBtn) playBtn.textContent = state.paused ? '▶' : '⏸';

    _renderSdkProgress();

    if (_sdkPaused) {
        _stopTicker();
    } else {
        _startTicker();
    }

    // Fire AFTER updating internal state + stopping the ticker so the
    // outgoing track's stale state can't re-trigger anything.
    if (looksLikeNaturalEnd && isAutoplayEnabled()) {
        const ourTrackId = getCurrentPreviewTrack()?.track_id;
        if (ourTrackId && _sdkAdvanceFiredFor !== ourTrackId) {
            _sdkAdvanceFiredFor = ourTrackId;
            _dbg('[SDK] natural end-of-track detected → nextPreview()');
            nextPreview();
        }
    }
}

/** Render seek bar + time labels from `_sdkLastPositionMs`/`Duration`. */
function _renderSdkProgress() {
    if (_sdkScrubberDragging) return;
    const seek = el('sdkPlayerSeek');
    if (seek && _sdkLastDurationMs > 0) {
        seek.value = String(Math.round((_sdkLastPositionMs / _sdkLastDurationMs) * 100));
    }
    const cur = el('sdkPlayerTimeCur');
    const dur = el('sdkPlayerTimeDur');
    if (cur) cur.textContent = formatMs(_sdkLastPositionMs);
    if (dur) dur.textContent = formatMs(_sdkLastDurationMs);
}

function _startTicker() {
    if (_tickerHandle !== null) return;
    _tickerHandle = setInterval(_tick, 250);
}

function _stopTicker() {
    if (_tickerHandle !== null) {
        clearInterval(_tickerHandle);
        _tickerHandle = null;
    }
}

function _tick() {
    if (_sdkPaused || _sdkLastDurationMs <= 0) return;
    const now = performance.now();
    const elapsed = now - _sdkPositionAnchorMs;
    const projected = Math.min(_sdkLastPositionMs + elapsed, _sdkLastDurationMs);

    // Update the displayed position without mutating the anchor — the
    // anchor is only updated by real state_changed events.
    const oldPos = _sdkLastPositionMs;
    _sdkLastPositionMs = projected;
    _renderSdkProgress();
    _sdkLastPositionMs = oldPos;

    // Auto-advance: once the projected position has reached the duration,
    // call nextPreview() once. _sdkAdvanceFiredFor latches the track id
    // so the same track end never fires twice.
    if (projected >= _sdkLastDurationMs - 100 && isAutoplayEnabled()) {
        const trackId = getCurrentPreviewTrack()?.track_id;
        if (trackId && _sdkAdvanceFiredFor !== trackId) {
            _sdkAdvanceFiredFor = trackId;
            _stopTicker();
            nextPreview();
        }
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
    _dbg('[SDK] playTrack() starting for', track.track_id, track.artist, '—', track.track);
    try {
        await Sdk.playTrack(track.track_id);
        _dbg('[SDK] playTrack() resolved');
    } catch (e) {
        _dbgError('[SDK] playTrack() failed:', e);
        throw e;
    }
}

function updateSdkMeta(track) {
    if (!track) return;
    const art = el('sdkPlayerArt');
    const wrap = el('sdkPlayerArtWrap');
    const url = track.cover_url || track.album_art || track.image_url || '';
    if (art && url) art.src = url;
    if (wrap) wrap.toggleAttribute('hidden', !url);
}

function showLoader() {
    el('previewLoader')?.removeAttribute('hidden');
    el('sdkPlayer')?.setAttribute('hidden', '');
    el('spotifyPreviewSlider')?.setAttribute('hidden', '');
}

function showSdkPanel() {
    _playbackMode = 'sdk';
    el('previewLoader')?.setAttribute('hidden', '');
    el('sdkPlayer')?.removeAttribute('hidden');
    el('spotifyPreviewSlider')?.setAttribute('hidden', '');
}

function showIframePanel() {
    _playbackMode = 'iframe';
    el('previewLoader')?.setAttribute('hidden', '');
    el('sdkPlayer')?.setAttribute('hidden', '');
    el('spotifyPreviewSlider')?.removeAttribute('hidden');
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

const RATE_HINT_KEY = 'spv_preview_rate_hint_seen';

function updatePreviewFeedbackState() {
    const actions = el('previewInlineActions');
    if (actions) actions.style.display = currentPreviewIndex >= 0 ? 'flex' : 'none';
}

function getCurrentPreviewTrack() {
    const tracks = getSourceTracks();
    return currentPreviewIndex >= 0 ? tracks[currentPreviewIndex] : null;
}

/**
 * Open the reason panel with no pre-selected polarity. User picks
 * Like or Dislike via the dual submit buttons at the bottom. (§6)
 */
export function openPreviewFeedbackPanel() {
    const track = getCurrentPreviewTrack();
    if (!track) return;
    const panel = el('previewFeedbackPanel');
    if (!panel) return;

    if (panel.classList.contains('visible')) {
        closePreviewFeedback();
        return;
    }

    panel.classList.remove('action-like', 'action-dislike');
    panel.classList.add('visible');

    const artistInput = el('previewFbArtist');
    const trackInput = el('previewFbTrack');
    const reasonInput = el('previewFbReason');
    if (artistInput) artistInput.value = track.artist || '';
    if (trackInput) trackInput.value = track.track || '';
    if (reasonInput) reasonInput.value = '';
}

export function closePreviewFeedback() {
    const panel = el('previewFeedbackPanel');
    if (panel) {
        panel.classList.remove('visible', 'action-like', 'action-dislike');
    }
}

/**
 * Quick submit-on-click from the SDK player's 👍/👎 buttons. No form,
 * empty reason. Dislike also strips the track from the Spotify playlist
 * and advances.
 */
export function quickLike() {
    return _submitQuickFeedback('like');
}

export function quickDislike() {
    return _submitQuickFeedback('dislike');
}

async function _submitQuickFeedback(action) {
    const track = getCurrentPreviewTrack();
    if (!track) return;
    await _postFeedbackAndReact(action, track.artist, track.track, null);
}

/**
 * Submit the reason-panel feedback with explicit polarity (Like or
 * Dislike button on the panel). Reads the form's artist/track/reason.
 */
export async function submitPreviewFeedback(action) {
    const artist = el('previewFbArtist').value.trim();
    const track = el('previewFbTrack').value.trim();
    const reason = el('previewFbReason').value.trim();

    if (!artist) { showAlert(i18n('feedback.artist_required', 'Artist is required.')); return; }

    const btnId = action === 'like' ? 'previewFbSubmitLike' : 'previewFbSubmitDislike';
    const submitBtn = el(btnId);
    if (submitBtn) { submitBtn.disabled = true; }

    try {
        await _postFeedbackAndReact(action, artist, track || null, reason || null);
    } finally {
        if (submitBtn) submitBtn.disabled = false;
    }
}

/** Resolve the Spotify playlist_id the currently-previewed track belongs to. */
function _getContextPlaylistId() {
    if (currentPreviewSource === 'review') {
        const picker = el('reviewPlaylistPicker');
        return picker && picker.value ? picker.value : null;
    }
    return State.lastGeneratedPlaylistId || null;
}

async function _postFeedbackAndReact(action, artist, track, reason) {
    try {
        const currentTrack = getCurrentPreviewTrack();
        const result = await postFeedback({
            action, artist, track, reason,
            playlistId: _getContextPlaylistId(),
            trackId: currentTrack && currentTrack.track_id,
        });
        if (!result.ok) {
            showAlert(i18n('msg.error_prefix', 'Error: {detail}').replace('{detail}', result.error));
            return;
        }
        const body = result.body;

        const trackLabel = track ? ` — ${track}` : '';
        const { showToast } = await import('./ui.js');

        if (action === 'dislike') {
            const removal = body && body.removal;
            if (removal && removal.removed) {
                showToast(i18n('feedback.quick_disliked_toast', '👎 Disliked & removed: {track}').replace('{track}', `${artist}${trackLabel}`));
            } else {
                const reasonText = (removal && removal.reason) || i18n('feedback.remove_unknown_reason', 'unknown');
                _dbgWarn('[feedback] dislike recorded but playlist removal failed:', removal);
                showToast(i18n('feedback.quick_disliked_not_removed_toast', '👎 Disliked: {track} (not removed from playlist: {reason})')
                    .replace('{track}', `${artist}${trackLabel}`)
                    .replace('{reason}', reasonText));
            }
        } else {
            showToast(i18n('feedback.quick_liked_toast', '👍 Liked: {track}').replace('{track}', `${artist}${trackLabel}`));
        }

        // Refresh the Getting-started checklist so the "3 tracks" item ticks.
        if (typeof window.refreshGettingStarted === 'function') {
            window.refreshGettingStarted();
        }

        _maybeTriggerRegenProfileTip();

        removeCurrentAndAdvance();
    } catch (e) {
        showAlert(i18n('msg.network_error', 'Network error: {detail}').replace('{detail}', e.message));
    }
}

/** First preview per session: pulse the player quick buttons + tip. */
function maybeShowRateHint() {
    try {
        if (localStorage.getItem(RATE_HINT_KEY) === '1') return;
        localStorage.setItem(RATE_HINT_KEY, '1');
    } catch (_) { /* ignore storage errors */ }

    const like = el('sdkQuickLike');
    const dislike = el('sdkQuickDislike');
    [like, dislike].forEach((btn) => {
        if (!btn) return;
        btn.classList.add('pulse');
        setTimeout(() => btn.classList.remove('pulse'), 4000);
    });
    if (window.Tips && typeof window.Tips.showTipById === 'function') {
        window.Tips.showTipById('first_preview_open');
    }
}

export async function previewDismiss() {
    const track = getCurrentPreviewTrack();
    if (!track) return;

    try {
        const { body } = await postRemove({
            artist: track.artist,
            track: track.track,
            playlistId: _getContextPlaylistId(),
            trackId: track.track_id,
        });
        const { showToast } = await import('./ui.js');
        if (body && body.removed) {
            showToast(i18n('feedback.removed_from_playlist', 'Removed from playlist: {track}').replace('{track}', `${track.artist} — ${track.track}`));
        } else {
            const reasonText = (body && body.reason) || i18n('feedback.remove_unknown_reason', 'unknown');
            _dbgWarn('[dismiss] playlist removal failed:', body);
            showToast(i18n('feedback.remove_failed', 'Could not remove from playlist: {reason}').replace('{reason}', reasonText));
        }
    } catch (e) {
        _dbgWarn('[dismiss] network error removing track:', e);
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
