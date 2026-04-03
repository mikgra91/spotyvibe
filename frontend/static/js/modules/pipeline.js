import * as State from './state.js';
import { showStatus, showStatusHtml, hidePlaylistLink, showPlaylistLink } from './ui.js';
import { checkCredentialStatus, checkSpotifyAuth } from './auth.js';
import { renderComponentWarnings } from './warnings.js';
import { getPlaylistModePayload, refreshDiscoverPlaylistPicker } from './playlist-mode.js';
import { getAudioFilters } from './audio-filters.js';
import { renderTracks } from './tracklist.js';
import { loadHistory } from './history.js';
import { populateReviewPlaylistPicker } from './review.js';

export function toggleGenerateBody() {
    const body = document.getElementById('generateBody');
    const btn = document.getElementById('generateToggleBtn');
    const isHidden = body.classList.toggle('hidden');
    if (btn) {
        btn.textContent = isHidden ? 'Show' : 'Hide';
        btn.setAttribute('aria-expanded', (!isHidden).toString());
    }
    const header = document.querySelector('#generateSection > .train-header');
    if (header) header.setAttribute('aria-expanded', (!isHidden).toString());
}

export function canGenerate() {
    return State.openaiKeySet && State.spotifyAuthStatus === 'authenticated' && State.profileTrained;
}

export function generateUUID() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
        const r = Math.random() * 16 | 0;
        return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
}

export function setGenerating(generating) {
    State.setIsGenerating(generating);
    const runBtn    = document.getElementById('runBtn');
    const cancelBtn = document.getElementById('cancelBtn');
    const useBtn    = document.getElementById('useTracksBtn');
    const loadArea  = document.getElementById('generateLoadingArea');

    runBtn.disabled  = generating;
    runBtn.textContent = generating ? '⏳ Generating…' : '▶ Generate & Create Playlist';

    cancelBtn.classList.toggle('hidden', !generating);

    useBtn.classList.toggle('hidden', !generating || State.partialTrackCount === 0);

    if (loadArea) {
        loadArea.classList.toggle('hidden', !generating);
        if (!generating) {
            const msg = document.getElementById('generateLoadingMsg');
            if (msg) msg.textContent = '';
        }
    }
}

export function updateUseTracksButton(count) {
    State.setPartialTrackCount(count);
    const useBtn = document.getElementById('useTracksBtn');
    if (State.isGenerating && count > 0) {
        useBtn.textContent = `▶ Use ${count} track${count !== 1 ? 's' : ''} now`;
        useBtn.classList.remove('hidden');
    } else {
        useBtn.classList.add('hidden');
    }
}

export async function runPipeline() {
    await Promise.all([checkCredentialStatus(), checkSpotifyAuth()]);
    renderComponentWarnings();

    if (!State.openaiKeySet) {
        showStatus('⚠️ OpenAI API key is missing. Open ⚙️ Settings.', 'error');
        return;
    }
    if (State.spotifyAuthStatus !== 'authenticated') {
        showStatus('⚠️ Spotify is not connected. Check the warning below the Generate button.', 'error');
        return;
    }

    if (!State.profileTrained) {
        showStatus('⚠️ Please train your taste profile first before generating suggestions.', 'error');
        return;
    }

    if (!canGenerate()) return;

    State.setPartialTrackCount(0);
    State.setCurrentRunId(generateUUID());
    State.setCurrentAbortController(new AbortController());
    setGenerating(true);
    showStatus('Starting pipeline…', 'info');
    hidePlaylistLink();

    const playlistPayload = getPlaylistModePayload();
    const audioFilters = getAudioFilters();
    if (audioFilters) playlistPayload.audio_filters = audioFilters;

    try {
        await _startSseStream(State.currentRunId, State.currentAbortController.signal, playlistPayload);
    } catch (e) {
        if (e.name === 'AbortError') {
            // Expected — cancelGeneration() was called, status already set
        } else if (e.name === 'TypeError' || e.message?.toLowerCase().includes('network')) {
            showSseDisconnectBanner();
        } else {
            showStatus('❌ Network error: ' + e.message, 'error');
        }
    } finally {
        setGenerating(false);
    }
}

/**
 * Internal: open the SSE stream for a run.
 * Extracted so resumeRun can re-use it.
 */
async function _startSseStream(runId, signal, payload) {
    const response = await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_id: runId, ...payload }),
        signal,
    });
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        let boundary;
        while ((boundary = buffer.indexOf('\n\n')) !== -1) {
            const chunk = buffer.substring(0, boundary);
            buffer = buffer.substring(boundary + 2);

            for (const line of chunk.split('\n')) {
                if (line.startsWith('data: ')) {
                    try {
                        handleStreamEvent(JSON.parse(line.substring(6)));
                    } catch (e) { /* skip malformed */ }
                }
            }
        }
    }

    if (buffer.trim()) {
        for (const line of buffer.split('\n')) {
            if (line.startsWith('data: ')) {
                try {
                    handleStreamEvent(JSON.parse(line.substring(6)));
                } catch (e) { /* skip malformed */ }
            }
        }
    }
}

export function showSseDisconnectBanner() {
    const savedRunId = State.currentRunId;
    showStatusHtml(
        '⚠️ Connection lost. <button onclick="resumeRun(\'' + savedRunId + '\')" class="btn btn-save" style="margin-left:8px;padding:4px 12px;font-size:0.82rem;">Resume</button>',
        'error'
    );
}

export async function resumeRun(runId) {
    if (!runId) return;
    try {
        const resp = await fetch(`/api/run/${runId}/status`);
        if (!resp.ok) { showStatus('Run no longer active.', 'info'); return; }
        const data = await resp.json();

        if (data.status === 'running') {
            // Re-initiate the SSE stream to continue receiving events
            showStatus(`⏳ Reconnecting… (${data.tracks_found} tracks found so far)`, 'info');
            State.setCurrentRunId(runId);
            State.setCurrentAbortController(new AbortController());
            setGenerating(true);

            try {
                await _startSseStream(runId, State.currentAbortController.signal, { resume: true });
            } catch (e) {
                if (e.name === 'AbortError') {
                    // user cancelled
                } else {
                    showSseDisconnectBanner();
                }
            } finally {
                setGenerating(false);
            }
        } else {
            showStatus(`Run state: ${data.status}, ${data.tracks_found} tracks found.`, 'info');
        }
    } catch (e) {
        showStatus('Could not recover run state.', 'error');
    }
}

/* ── Auto-resume SSE on visibility change (mobile app foreground) ── */
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') return;
    // If we were generating but the connection was lost, try to resume
    if (State.currentRunId && !State.isGenerating) {
        // Check if a disconnect banner is showing (status contains "Connection lost")
        const statusEl = document.getElementById('status');
        if (statusEl && statusEl.textContent.includes('Connection lost')) {
            resumeRun(State.currentRunId);
        }
    }
});

export async function cancelGeneration() {
    if (!State.isGenerating || !State.currentRunId) return;

    showStatus('⛔ Cancelling…', 'info');

    if (State.currentAbortController) State.currentAbortController.abort();

    try {
        await fetch('/api/cancel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ run_id: State.currentRunId, finalize: false }),
        });
    } catch (e) { /* ignore */ }

    showStatus('⛔ Generation cancelled.', 'info');
}

export async function useCurrentTracks() {
    if (!State.isGenerating || !State.currentRunId || State.partialTrackCount === 0) return;

    const useBtn = document.getElementById('useTracksBtn');
    useBtn.disabled = true;
    useBtn.textContent = '⏳ Finalising…';

    showStatus(`⏳ Creating playlist with ${State.partialTrackCount} track(s)…`, 'info');

    try {
        await fetch('/api/cancel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ run_id: State.currentRunId, finalize: true }),
        });
    } catch (e) { /* ignore */ }
}

export function handleStreamEvent(event) {
    switch (event.type) {
        case 'progress':
            showStatus('⏳ ' + event.message, 'info');
            break;
        case 'batch_verified':
            updateUseTracksButton(event.count);
            break;
        case 'cancelled':
            showStatus('⛔ ' + event.message, 'info');
            break;
        case 'result': {
            State.setSuggestions(event.playlist || []);
            renderTracks();
            const _batchCount = State.suggestions.length;
            if (State.historyBodyOpen) loadHistory();
            if (event.playlist_url) showPlaylistLink(event.playlist_url);
            const parts = [
                event.was_cancelled
                    ? `⛔ Generation stopped early. Playlist created with ${_batchCount} track(s).`
                    : `✅ ${_batchCount} suggestions generated.`
            ];
            if (event.added) parts.push(`${event.added} new track(s) added to playlist.`);
            if (event.not_found && event.not_found.length)
                parts.push(`${event.not_found.length} track(s) not found on Spotify.`);
            showStatus(parts.join(' '), event.was_cancelled ? 'info' : 'success');
            // Playlist was created or modified — refresh both pickers
            refreshDiscoverPlaylistPicker().then(() => populateReviewPlaylistPicker());
            break;
        }
        case 'error':
            showStatus('❌ ' + event.message, 'error');
            break;
    }
}
