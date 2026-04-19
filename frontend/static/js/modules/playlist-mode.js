import * as State from './state.js';
import { i18n } from './i18n.js';
import { el } from './dom.js';

const LAST_PLAYLIST_KEY = 'sv.playlist.last_id';

function _readLastPlaylistId() {
    try { return localStorage.getItem(LAST_PLAYLIST_KEY) || null; } catch (_) { return null; }
}

export function rememberLastPlaylistId(id) {
    if (!id) return;
    try { localStorage.setItem(LAST_PLAYLIST_KEY, id); } catch (_) { /* ignore */ }
}

export function getPlaylistMode() {
    const checked = document.querySelector('input[name="playlist_mode"]:checked');
    return checked ? checked.value : 'default';
}

/**
 * Fetch playlists (or use shared cache) and render them into #playlistPicker.
 */
async function loadDiscoverPicker() {
    const sel = el('playlistPicker');
    if (!sel) return;

    let playlists = State.cachedPlaylists;
    if (!playlists) {
        sel.innerHTML = `<option value="">${i18n('playlist_mode.loading', 'Loading…')}</option>`;
        try {
            const resp = await fetch('/api/playlists');
            const data = await resp.json();
            playlists = data.playlists || [];
            State.setCachedPlaylists(playlists);
        } catch (e) {
            sel.innerHTML = `<option value="">${i18n('playlist_mode.error', 'Error loading playlists')}</option>`;
            return;
        }
    }

    const prevValue = sel.value || _readLastPlaylistId();
    sel.innerHTML = '';
    if (playlists.length === 0) {
        sel.innerHTML = `<option value="">${i18n('playlist_mode.empty', 'No playlists found')}</option>`;
    } else {
        playlists.forEach(pl => {
            const opt = document.createElement('option');
            opt.value = pl.id;
            opt.textContent = pl.name;
            sel.appendChild(opt);
        });
        // Restore previous selection (current in-DOM value, or last used across sessions)
        if (prevValue && sel.querySelector(`option[value="${prevValue}"]`)) {
            sel.value = prevValue;
        }
    }
}

export async function onPlaylistModeChange() {
    const mode = getPlaylistMode();
    const nameRow = el('playlistNameRow');
    const pickerRow = el('playlistPickerRow');
    nameRow.classList.toggle('hidden', mode !== 'create');
    pickerRow.classList.toggle('hidden', mode !== 'append' && mode !== 'replace');

    if ((mode === 'append' || mode === 'replace') && pickerRow && !pickerRow.dataset.loaded) {
        pickerRow.dataset.loaded = '1';
        await loadDiscoverPicker();
    }
}

/**
 * Invalidate the shared playlist cache and re-render the Discover picker
 * if it was previously loaded.
 */
export async function refreshDiscoverPlaylistPicker() {
    State.invalidateCachedPlaylists();
    const pickerRow = el('playlistPickerRow');
    if (pickerRow && pickerRow.dataset.loaded) {
        await loadDiscoverPicker();
    }
}

export function getPlaylistModePayload() {
    const mode = getPlaylistMode();
    const payload = { playlist_mode: mode };
    if (mode === 'create') {
        const name = (el('playlistNameInput')?.value || '').trim();
        if (name) payload.playlist_name = name;
    } else if (mode === 'append' || mode === 'replace') {
        const id = el('playlistPicker')?.value;
        if (id) {
            payload.playlist_id = id;
            rememberLastPlaylistId(id);
        }
    }
    return payload;
}

/**
 * On page load, if the user previously used a playlist, pre-select "Append"
 * mode pointing at that playlist so they don't accidentally create a new
 * "My AI Playlist" duplicate each time they return.
 */
export async function initPlaylistMode() {
    const lastId = _readLastPlaylistId();
    const picker = el('playlistPicker');
    if (picker) {
        picker.addEventListener('change', () => {
            if (picker.value) rememberLastPlaylistId(picker.value);
        });
    }
    if (!lastId) return;

    const appendRadio = document.querySelector('input[name="playlist_mode"][value="append"]');
    if (!appendRadio) return;
    appendRadio.checked = true;

    const nameRow = el('playlistNameRow');
    const pickerRow = el('playlistPickerRow');
    if (nameRow) nameRow.classList.add('hidden');
    if (pickerRow) {
        pickerRow.classList.remove('hidden');
        pickerRow.dataset.loaded = '1';
    }
    await loadDiscoverPicker();
    if (picker) {
        if (picker.querySelector(`option[value="${lastId}"]`)) {
            picker.value = lastId;
        }
    }
}

/**
 * Ensure the cached playlists are loaded (for duplicate checks etc.).
 * Returns the playlist array.
 */
export async function ensurePlaylistsLoaded() {
    if (State.cachedPlaylists) return State.cachedPlaylists;
    try {
        const resp = await fetch('/api/playlists');
        const data = await resp.json();
        const playlists = data.playlists || [];
        State.setCachedPlaylists(playlists);
        return playlists;
    } catch (_) {
        return [];
    }
}

/**
 * Programmatically switch to "Append to existing" mode and select a specific playlist.
 * Used after a successful "create" run to let the user continue appending.
 */
export async function switchToAppendMode(playlistId) {
    // Check the "append" radio button
    const appendRadio = document.querySelector('input[name="playlist_mode"][value="append"]');
    if (!appendRadio) return;
    appendRadio.checked = true;

    // Toggle row visibility
    const nameRow = el('playlistNameRow');
    const pickerRow = el('playlistPickerRow');
    if (nameRow) nameRow.classList.add('hidden');
    if (pickerRow) {
        pickerRow.classList.remove('hidden');
        pickerRow.dataset.loaded = '1';
    }

    // Refresh picker and select the target playlist
    await refreshDiscoverPlaylistPicker();
    const sel = el('playlistPicker');
    if (sel && playlistId) {
        sel.value = playlistId;
    }
}
