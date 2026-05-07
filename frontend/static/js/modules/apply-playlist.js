/**
 * Apply Playlist module — handles the modal for creating/appending/replacing
 * a Spotify playlist from the staged suggestion list.
 */
import * as State from './state.js';
import { showToast, showAlert, showPlaylistLink, showConfirm } from './ui.js';
import { i18n } from './i18n.js';
import { el } from './dom.js';
import { ensurePlaylistsLoaded, refreshDiscoverPlaylistPicker, rememberLastPlaylistId } from './playlist-mode.js';
import { populateReviewPlaylistPicker } from './review.js';
import { renderTracks } from './tracklist.js';

/**
 * Open the apply-playlist modal.
 */
export async function openApplyModal() {
    const tracks = State.suggestions.filter(Boolean);
    if (tracks.length === 0) {
        showAlert(i18n('apply.no_tracks', 'No suggestions to apply. Generate some first.'));
        return;
    }

    const modal = el('applyPlaylistModal');
    if (!modal) return;

    // Reset state
    const createRadio = el('applyModeCreate');
    if (createRadio) createRadio.checked = true;
    _onModeChange();

    modal.classList.remove('hidden');
    modal.setAttribute('aria-hidden', 'false');

    // Load playlists for picker
    try {
        const playlists = await ensurePlaylistsLoaded();
        const picker = el('applyPlaylistPicker');
        if (picker && playlists) {
            picker.innerHTML = '';
            playlists.forEach(pl => {
                const opt = document.createElement('option');
                opt.value = pl.id;
                opt.textContent = pl.name;
                picker.appendChild(opt);
            });
        }
    } catch (_) { /* ignore */ }
}

/**
 * Close the apply-playlist modal.
 */
export function closeApplyModal() {
    const modal = el('applyPlaylistModal');
    if (modal) {
        modal.classList.add('hidden');
        modal.setAttribute('aria-hidden', 'true');
    }
}

/**
 * Handle mode radio change inside the apply modal.
 */
export function _onModeChange() {
    const mode = _getSelectedMode();
    const nameRow = el('applyPlaylistNameRow');
    const pickerRow = el('applyPlaylistPickerRow');
    if (nameRow) nameRow.classList.toggle('hidden', mode !== 'create');
    if (pickerRow) pickerRow.classList.toggle('hidden', mode !== 'append' && mode !== 'replace');
}

function _getSelectedMode() {
    const checked = document.querySelector('input[name="apply_playlist_mode"]:checked');
    return checked ? checked.value : 'create';
}

/**
 * Submit: apply staged tracks to Spotify playlist.
 */
export async function submitApply() {
    const tracks = State.suggestions.filter(Boolean);
    if (tracks.length === 0) {
        showAlert(i18n('apply.no_tracks', 'No suggestions to apply.'));
        return;
    }

    const mode = _getSelectedMode();
    let playlistName = null;
    let playlistId = null;

    if (mode === 'create') {
        const nameInput = el('applyPlaylistNameInput');
        playlistName = (nameInput?.value || '').trim() || null;
        // Duplicate check
        if (playlistName) {
            const playlists = await ensurePlaylistsLoaded();
            const duplicate = playlists.some(pl => pl.name.toLowerCase() === playlistName.toLowerCase());
            if (duplicate) {
                const msg = i18n('playlist_mode.duplicate_confirm', 'A playlist named "{name}" already exists.\n\nDo you want to create a duplicate?')
                    .replace('{name}', playlistName);
                const confirmed = await showConfirm(msg);
                if (!confirmed) return;
            }
        }
    } else {
        const picker = el('applyPlaylistPicker');
        playlistId = picker?.value || null;
        if (!playlistId) {
            showAlert(i18n('apply.select_playlist', 'Please select a playlist.'));
            return;
        }
    }

    const btn = el('applySubmitBtn');
    if (btn) btn.disabled = true;

    try {
        const resp = await fetch('/api/apply-playlist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tracks,
                playlist_mode: mode,
                playlist_name: playlistName,
                playlist_id: playlistId,
            }),
        });
        const data = await resp.json();

        if (!resp.ok) {
            showAlert(i18n('msg.error_prefix', 'Error: {detail}').replace('{detail}', data.error || resp.status));
            return;
        }

        // Success
        if (data.playlist_url) showPlaylistLink(data.playlist_url);
        if (data.playlist_id) {
            State.setLastGeneratedPlaylistId(data.playlist_id);
            rememberLastPlaylistId(data.playlist_id);
        }

        showToast(
            i18n('apply.success', '✅ Playlist {action} with {count} track(s).')
                .replace('{action}', i18n(`apply.action_${mode}`, mode))
                .replace('{count}', data.added || tracks.length)
        );

        // Clear the staging list
        State.setSuggestions([]);
        renderTracks();
        closeApplyModal();

        // Refresh playlist pickers
        refreshDiscoverPlaylistPicker().then(() => {
            populateReviewPlaylistPicker();
        });

    } catch (e) {
        showAlert(i18n('msg.network_error', 'Network error: {detail}').replace('{detail}', e.message));
    } finally {
        if (btn) btn.disabled = false;
    }
}

/**
 * Clear all suggestions from the staging list.
 */
export function clearSuggestions() {
    State.setSuggestions([]);
    renderTracks();
    showToast(i18n('apply.cleared', 'Suggestion list cleared.'));
}

