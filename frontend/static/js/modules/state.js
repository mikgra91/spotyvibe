import { i18n } from './i18n.js';
import { el } from './dom.js';

export let suggestions = [];
export let openFormIndex = null;
export let openFormAction = null;
export let spotifyAuthStatus = 'unknown';
export let openaiKeySet = false;
export let llmApiKeyRequired = true;
export let userProfileEditMode = false;
export let debugControlsAvailable = true;
export let profileTrained = false;
export let selectedModel = '';
export let gptLanguage = '';
export let historyBodyOpen = false;
export let currentRunId = null;
export let currentAbortController = null;
export let isGenerating = false;
export let partialTrackCount = 0;
export let helpLoaded = false;
export let reviewTracks = [];
export let cachedPlaylists = null;
const _LAST_PID_KEY = 'sv.lastGeneratedPlaylistId';
export let lastGeneratedPlaylistId = (() => {
    try { return localStorage.getItem(_LAST_PID_KEY) || null; } catch { return null; }
})();

export function setSuggestions(val) { suggestions = val; }
export function spliceSuggestion(idx) {
    suggestions[idx] = null;
    const maxSize = window._maxSongListSize || 100;
    const count = suggestions.filter(Boolean).length;
    const counterEl = el('songlistCounter');
    if (counterEl) counterEl.textContent = i18n('songlist.counter', '{count} / {max} songs').replace('{count}', count).replace('{max}', maxSize);
}
// Bug-1 fix (2026-05-30): liking a track must KEEP it in the discover
// list (so it can still be applied to a playlist) and mark it liked,
// rather than removing it like a dislike does. Mutates the live object
// reference so a subsequent renderTracks() preserves the marker.
export function markSuggestionLiked(idx, liked = true) {
    const t = suggestions[idx];
    if (t) t._liked = liked;
}
export function markReviewTrackLiked(idx, liked = true) {
    const t = reviewTracks[idx];
    if (t) t._liked = liked;
}
export function setOpenFormIndex(val) { openFormIndex = val; }
export function setOpenFormAction(val) { openFormAction = val; }
export function setSpotifyAuthStatus(val) { spotifyAuthStatus = val; }
export function setOpenaiKeySet(val) { openaiKeySet = val; }
export function setLlmApiKeyRequired(val) { llmApiKeyRequired = val; }
export function setUserProfileEditMode(val) { userProfileEditMode = val; }
export function setDebugControlsAvailable(val) { debugControlsAvailable = val; }
export function setProfileTrained(val) { profileTrained = val; }
export function setSelectedModel(val) { selectedModel = val; }
export function setGptLanguage(val) { gptLanguage = val; }
export function setHistoryBodyOpen(val) { historyBodyOpen = val; }
export function setCurrentRunId(val) { currentRunId = val; }
export function setCurrentAbortController(val) { currentAbortController = val; }
export function setIsGenerating(val) { isGenerating = val; }
export function setPartialTrackCount(val) { partialTrackCount = val; }
export function setHelpLoaded(val) { helpLoaded = val; }
export function setReviewTracks(val) { reviewTracks = val; }
export function spliceReviewTrack(idx) {
    reviewTracks[idx] = null;
    const count = reviewTracks.filter(Boolean).length;
    const counterEl = el('reviewTrackCounter');
    if (counterEl) counterEl.textContent = i18n('review.track_count', '{count} track(s)').replace('{count}', count);
}
export function setCachedPlaylists(val) { cachedPlaylists = val; }
export function invalidateCachedPlaylists() { cachedPlaylists = null; }
export function setLastGeneratedPlaylistId(val) {
    lastGeneratedPlaylistId = val || null;
    try {
        if (val) localStorage.setItem(_LAST_PID_KEY, val);
        else localStorage.removeItem(_LAST_PID_KEY);
    } catch { /* storage unavailable */ }
}

export function resetSessionState() {
    suggestions = [];
    reviewTracks = [];
    cachedPlaylists = null;
    openFormIndex = null;
    openFormAction = null;
    currentRunId = null;
    partialTrackCount = 0;
}
