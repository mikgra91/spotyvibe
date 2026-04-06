import * as State from './state.js';
import { i18n } from './i18n.js';

export function getPlaylistMode() {
    const checked = document.querySelector('input[name="playlist_mode"]:checked');
    return checked ? checked.value : 'default';
}

/**
 * Fetch playlists (or use shared cache) and render them into #playlistPicker.
 */
async function loadDiscoverPicker() {
    const sel = document.getElementById('playlistPicker');
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

    const prevValue = sel.value;
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
        // Restore previous selection if still present
        if (prevValue && sel.querySelector(`option[value="${prevValue}"]`)) {
            sel.value = prevValue;
        }
    }
}

export async function onPlaylistModeChange() {
    const mode = getPlaylistMode();
    const nameRow = document.getElementById('playlistNameRow');
    const pickerRow = document.getElementById('playlistPickerRow');
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
    const pickerRow = document.getElementById('playlistPickerRow');
    if (pickerRow && pickerRow.dataset.loaded) {
        await loadDiscoverPicker();
    }
}

export function getPlaylistModePayload() {
    const mode = getPlaylistMode();
    const payload = { playlist_mode: mode };
    if (mode === 'create') {
        const name = (document.getElementById('playlistNameInput')?.value || '').trim();
        if (name) payload.playlist_name = name;
    } else if (mode === 'append' || mode === 'replace') {
        const id = document.getElementById('playlistPicker')?.value;
        if (id) payload.playlist_id = id;
    }
    return payload;
}
