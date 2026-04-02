import * as State from './state.js';

let currentPreviewIndex = -1;

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
}

/** Returns only tracks that have a track_id (previewable). Preserves original index. */
function getPreviewableTracks() {
    return State.suggestions
        .map((t, i) => t ? { ...t, _origIdx: i } : null)
        .filter(t => t && t.track_id);
}

function loadTrackByIndex(idx) {
    const track = State.suggestions[idx];
    if (!track || !track.track_id) return;
    currentPreviewIndex = idx;

    replaceIframe(embedUrl(track.track_id, true));

    const titleEl = document.getElementById('spotifyPreviewTitle');
    if (titleEl) titleEl.textContent = `${track.artist} — ${track.track}`;

    updateNavState();
}

export function openPreviewOverlay(trackId, title) {
    const overlay = document.getElementById('spotifyPreviewOverlay');
    if (!overlay || !trackId) return;

    // Determine the index in suggestions
    currentPreviewIndex = State.suggestions.findIndex(t => t && t.track_id === trackId);

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
