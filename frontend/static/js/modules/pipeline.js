import * as State from './state.js';
import { showStatus, showStatusHtml, hidePlaylistLink, showPlaylistLink, showConfirm } from './ui.js';
import { checkCredentialStatus, checkSpotifyAuth } from './auth.js';
import { renderComponentWarnings } from './warnings.js';
import { getPlaylistModePayload, getPlaylistMode, refreshDiscoverPlaylistPicker, ensurePlaylistsLoaded, switchToAppendMode, rememberLastPlaylistId } from './playlist-mode.js';
import { getAudioFilters } from './audio-filters.js';
import { renderTracks } from './tracklist.js';
import { loadHistory } from './history.js';
import { populateReviewPlaylistPicker } from './review.js';
import { resetDashboard } from './taste_dashboard.js';
import { i18n, localizedError } from './i18n.js';
import { el } from './dom.js';
import { estimate as estimateCost, recordRunSpend } from './cost_estimate.js';

let _runPlaylistMode = null;  // playlist mode at time of generation (for auto-switch)

export function toggleGenerateBody() {
    const body = el('generateBody');
    const btn = el('generateToggleBtn');
    const isHidden = body.classList.toggle('hidden');
    if (btn) {
        btn.textContent = isHidden ? i18n('btn.show', 'Show') : i18n('btn.hide', 'Hide');
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
    const runBtn    = el('runBtn');
    const cancelBtn = el('cancelBtn');
    const useBtn    = el('useTracksBtn');
    const loadArea  = el('generateLoadingArea');

    runBtn.disabled  = generating;
    runBtn.textContent = generating ? i18n('msg.generating', '⏳ Generating…') : '▶ ' + i18n('btn.generate', 'Generate & Create Playlist');

    cancelBtn.classList.toggle('hidden', !generating);

    useBtn.classList.toggle('hidden', !generating || State.partialTrackCount === 0);

    if (loadArea) {
        loadArea.classList.toggle('hidden', !generating);
        if (generating) {
            // Scroll the loading area into view so the user gets a clear visual signal
            // that the click was registered. Especially important on small screens
            // where the spinner might otherwise be below the fold.
            try { loadArea.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (_) { /* older browsers */ }
        } else {
            const msg = el('generateLoadingMsg');
            if (msg) msg.textContent = '';
        }
    }
}

export function updateUseTracksButton(count) {
    State.setPartialTrackCount(count);
    const useBtn = el('useTracksBtn');
    if (State.isGenerating && count > 0) {
        useBtn.textContent = '▶ ' + i18n('generate.use_tracks_now', 'Use {count} tracks now').replace('{count}', count);
        useBtn.classList.remove('hidden');
    } else {
        useBtn.classList.add('hidden');
    }
}

export async function runPipeline() {
    await Promise.all([checkCredentialStatus(), checkSpotifyAuth()]);
    renderComponentWarnings();

    if (!State.openaiKeySet) {
        showStatus(i18n('msg.openai_key_missing', '⚠️ OpenAI API key is missing. Open ⚙️ Settings.'), 'error');
        return;
    }
    if (State.spotifyAuthStatus !== 'authenticated') {
        showStatus(i18n('msg.spotify_not_connected', '⚠️ Spotify is not connected. Check the warning below the Generate button.'), 'error');
        return;
    }

    if (!State.profileTrained) {
        showStatus(i18n('pipeline.train_first', '⚠️ Please train your taste profile first before generating suggestions.'), 'error');
        return;
    }

    if (!canGenerate()) return;

    // Duplicate playlist name check (only for "create" mode)
    const preMode = getPlaylistMode();
    if (preMode === 'create') {
        const nameInput = el('playlistNameInput');
        const desiredName = (nameInput?.value || '').trim();
        if (desiredName) {
            const playlists = await ensurePlaylistsLoaded();
            const duplicate = playlists.some(pl => pl.name.toLowerCase() === desiredName.toLowerCase());
            if (duplicate) {
                const msg = i18n('playlist_mode.duplicate_confirm', 'A playlist named "{name}" already exists.\n\nDo you want to create a duplicate?')
                    .replace('{name}', desiredName);
                const confirmed = await showConfirm(msg);
                if (!confirmed) return;
                const suffix = i18n('playlist_mode.duplicate_suffix', '_Duplicate');
                nameInput.value = desiredName + suffix;
            }
        }
    }

    State.setPartialTrackCount(0);
    State.setCurrentRunId(generateUUID());
    State.setCurrentAbortController(new AbortController());
    setGenerating(true);
    showStatus(i18n('pipeline.starting', 'Starting pipeline…'), 'info');
    hidePlaylistLink();

    const playlistPayload = getPlaylistModePayload();
    _runPlaylistMode = playlistPayload.playlist_mode || 'default';
    const audioFilters = getAudioFilters();
    if (audioFilters) playlistPayload.audio_filters = audioFilters;
    const emergingOnly = el('emergingArtistsCheckbox')?.checked || false;
    if (emergingOnly) playlistPayload.emerging_only = true;

    // Wave 2: temperature from exploration slider
    try {
        const Exploration = window._explorationModule;
        if (Exploration) {
            const temp = Exploration.getTemperature();
            if (temp != null) playlistPayload.temperature = temp;
        }
    } catch (_) { /* ignore */ }

    // Wave 2: playlist size from shared slider (overrides settings modal)
    const sizeSlider = document.querySelector('.gen-size-slider');
    if (sizeSlider) {
        playlistPayload.playlist_size = parseInt(sizeSlider.value, 10);
    }

    try {
        await _startSseStream(State.currentRunId, State.currentAbortController.signal, playlistPayload);
    } catch (e) {
        if (e.name === 'AbortError') {
            // Expected — cancelGeneration() was called, status already set
        } else if (e.name === 'TypeError' || e.message?.toLowerCase().includes('network')) {
            showSseDisconnectBanner();
        } else {
            showStatus(i18n('msg.network_error', '❌ Network error: {detail}').replace('{detail}', e.message), 'error');
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
        i18n('pipeline.connection_lost', '⚠️ Connection lost.') + ' <button onclick="resumeRun(\'' + esc(savedRunId) + '\')" class="btn btn-save" style="margin-left:8px;padding:4px 12px;font-size:0.82rem;">' + i18n('pipeline.resume', 'Resume') + '</button>',
        'error'
    );
}

export async function resumeRun(runId) {
    if (!runId) return;
    try {
        const resp = await fetch(`/api/run/${runId}/status`);
        if (!resp.ok) { showStatus(i18n('pipeline.run_inactive', 'Run no longer active.'), 'info'); return; }
        const data = await resp.json();

        if (data.status === 'running') {
            showStatus(i18n('pipeline.reconnecting', '⏳ Reconnecting… ({count} tracks found so far)').replace('{count}', data.tracks_found), 'info');
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
            showStatus(i18n('pipeline.run_state', 'Run state: {status}, {count} tracks found.').replace('{status}', data.status).replace('{count}', data.tracks_found), 'info');
        }
    } catch (e) {
        showStatus(i18n('pipeline.recover_failed', 'Could not recover run state.'), 'error');
    }
}

/* ── Auto-resume SSE on visibility change (mobile app foreground) ── */
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') return;
    // If we were generating but the connection was lost, try to resume
    if (State.currentRunId && !State.isGenerating) {
        // Check if a disconnect banner is showing (status contains "Connection lost")
        const statusEl = el('status');
        if (statusEl && statusEl.textContent.includes('Connection lost')) {
            resumeRun(State.currentRunId);
        }
    }
});

export async function cancelGeneration() {
    if (!State.isGenerating || !State.currentRunId) return;

    showStatus(i18n('pipeline.cancelling', '⛔ Cancelling…'), 'info');

    if (State.currentAbortController) State.currentAbortController.abort();

    try {
        await fetch('/api/cancel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ run_id: State.currentRunId, finalize: false }),
        });
    } catch (e) { /* ignore */ }

    showStatus(i18n('pipeline.cancelled', '⛔ Generation cancelled.'), 'info');
}

export async function useCurrentTracks() {
    if (!State.isGenerating || !State.currentRunId || State.partialTrackCount === 0) return;

    const useBtn = el('useTracksBtn');
    useBtn.disabled = true;
    useBtn.textContent = i18n('pipeline.finalising', '⏳ Finalising…');

    showStatus(i18n('pipeline.creating_playlist', '⏳ Creating playlist with {count} track(s)…').replace('{count}', State.partialTrackCount), 'info');

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
        case 'progress': {
            let msg = event.message;
            if (event.emerging_filtered != null) {
                msg = i18n('pipeline.emerging_batch_filtered', 'Batch: {count} track(s) filtered out (emerging artists only).').replace('{count}', event.emerging_filtered);
            }
            showStatus('⏳ ' + msg, 'info');
            break;
        }
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

            // P0.1: add this run's estimated cost to the session-cumulative
            // spend display. Estimate is provider-side cost only; Spotify is free.
            try {
                const _modelEl = el('settings-model-freetext');
                let _model = '';
                if (_modelEl && !_modelEl.classList.contains('hidden')) _model = _modelEl.value.trim();
                if (!_model) {
                    const _sel = el('settings-model');
                    if (_sel) _model = _sel.value;
                }
                if (_model && _batchCount > 0) {
                    estimateCost({ model: _model, profileText: '', tracks: _batchCount }).then(r => {
                        if (r && r.cost) recordRunSpend(r.cost);
                    });
                }
            } catch (_) { /* ignore */ }
            if (event.playlist_url) showPlaylistLink(event.playlist_url);
            if (event.playlist_id) {
                State.setLastGeneratedPlaylistId(event.playlist_id);
                rememberLastPlaylistId(event.playlist_id);
            }
            const parts = [
                event.was_cancelled
                    ? i18n('pipeline.stopped_early', '⛔ Generation stopped early. Playlist created with {count} track(s).').replace('{count}', _batchCount)
                    : i18n('pipeline.suggestions_generated', '✅ {count} suggestions generated.').replace('{count}', _batchCount)
            ];
            if (event.added) parts.push(i18n('pipeline.tracks_added', '{count} new track(s) added to playlist.').replace('{count}', event.added));
            if (event.not_found && event.not_found.length)
                parts.push(i18n('pipeline.tracks_not_found', '{count} track(s) not found on Spotify.').replace('{count}', event.not_found.length));
            if (event.emerging_shown != null && event.emerging_checked != null)
                parts.push(i18n('pipeline.emerging_filter_result', 'Showing {shown} of {checked} checked tracks — only tracks by recently emerged artists are included.').replace('{shown}', event.emerging_shown).replace('{checked}', event.emerging_checked));
            showStatus(parts.join(' '), event.was_cancelled ? 'info' : 'success');
            // Playlist was created or modified — refresh both pickers
            refreshDiscoverPlaylistPicker().then(() => {
                populateReviewPlaylistPicker();
                // Auto-switch to "append" mode after a "create" run
                if (_runPlaylistMode === 'create' && event.playlist_id) {
                    switchToAppendMode(event.playlist_id);
                }
            });

            // Refresh taste dashboard and run history with the new data
            resetDashboard();
            loadHistory();

            // Wave 3: Tip triggers after successful generation
            if (window.Tips) {
                window.Tips.maybeTrigger('first_generation_complete');
                // Track generation count for the "five generations" tip
                try {
                    const genCount = parseInt(localStorage.getItem('sv.gen_count') || '0', 10) + 1;
                    localStorage.setItem('sv.gen_count', genCount.toString());
                    if (genCount >= 5) window.Tips.maybeTrigger('five_generations');
                } catch (_) { /* ignore */ }
            }
            break;
        }
        case 'error': {
            const localized = localizedError(
                { error: event.message, error_key: event.error_key, error_params: event.error_params },
                event.message
            );
            showStatus('❌ ' + localized, 'error');
            break;
        }
    }
}
