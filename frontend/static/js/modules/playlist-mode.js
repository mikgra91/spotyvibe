export function getPlaylistMode() {
    const checked = document.querySelector('input[name="playlist_mode"]:checked');
    return checked ? checked.value : 'default';
}

export async function onPlaylistModeChange() {
    const mode = getPlaylistMode();
    const nameRow = document.getElementById('playlistNameRow');
    const pickerRow = document.getElementById('playlistPickerRow');
    nameRow.classList.toggle('hidden', mode !== 'create');
    pickerRow.classList.toggle('hidden', mode !== 'append' && mode !== 'replace');

    if ((mode === 'append' || mode === 'replace') && pickerRow && !pickerRow.dataset.loaded) {
        pickerRow.dataset.loaded = '1';
        const sel = document.getElementById('playlistPicker');
        sel.innerHTML = '<option value="">Loading…</option>';
        try {
            const resp = await fetch('/api/playlists');
            const data = await resp.json();
            sel.innerHTML = '';
            (data.playlists || []).forEach(pl => {
                const opt = document.createElement('option');
                opt.value = pl.id;
                opt.textContent = `${pl.name} (${pl.track_count} tracks)`;
                sel.appendChild(opt);
            });
            if (!data.playlists || data.playlists.length === 0)
                sel.innerHTML = '<option value="">No playlists found</option>';
        } catch (e) {
            sel.innerHTML = '<option value="">Error loading playlists</option>';
        }
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
