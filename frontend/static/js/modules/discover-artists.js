/**
 * Discover Artists — find NEW artists matching the taste profile, each
 * with a few real tracks to start. Separate from the Discover Tracks
 * pipeline: one POST to /api/discover_artists, client-rendered results.
 * Discovered tracks verified on Spotify can be applied to a playlist via
 * the shared apply-playlist modal.
 */
import { el } from './dom.js';
import { i18n } from './i18n.js';
import { showToast, showAlert, esc } from './ui.js';
import { openApplyModal } from './apply-playlist.js';

// Last discovered artists (raw objects from /api/discover_artists).
let _artists = [];

export function toggleDiscoverArtistsBody() {
    const body = el('discoverArtistsBody');
    const btn = el('discoverArtistsToggleBtn');
    if (!body) return;
    const isHidden = body.classList.toggle('hidden');
    const expanded = (!isHidden).toString();
    if (btn) {
        btn.textContent = isHidden ? i18n('btn.show', 'Show') : i18n('btn.hide', 'Hide');
        btn.setAttribute('aria-expanded', expanded);
    }
    const header = document.querySelector('#discoverArtistsSection > .train-header');
    if (header) header.setAttribute('aria-expanded', expanded);
}

const _NOTCH_KEYS = {
    1: 'gen.exploration_notch_1', 2: 'gen.exploration_notch_2',
    3: 'gen.exploration_notch_3', 4: 'gen.exploration_notch_4',
    5: 'gen.exploration_notch_5',
};

// Keep the slider value badges in sync with the inputs.
function _syncSliders() {
    const count = el('artistCount');
    const countVal = el('artistCountValue');
    if (count && countVal) countVal.textContent = count.value;
    const expl = el('artistExploration');
    const explVal = el('artistExplorationValue');
    if (expl && explVal) {
        const key = _NOTCH_KEYS[expl.value] || 'gen.exploration_notch_3';
        explVal.textContent = i18n(key, 'Balanced');
        // Keep data-i18n current so a language switch re-localises the notch.
        explVal.setAttribute('data-i18n', key);
    }
}

function _setActionsVisible(visible) {
    const row = el('discoverArtistsActions');
    if (row) row.classList.toggle('hidden', !visible);
}

export async function runDiscoverArtists() {
    const btn = el('discoverArtistsBtn');
    const loadArea = el('discoverArtistsLoadingArea');
    const loadMsg = el('discoverArtistsLoadingMsg');
    const artistCount = parseInt(el('artistCount')?.value || '8', 10);
    const exploration = parseInt(el('artistExploration')?.value || '3', 10);

    if (btn) btn.disabled = true;
    if (loadArea) loadArea.classList.remove('hidden');
    if (loadMsg) loadMsg.textContent = i18n('artists.loading', 'Discovering artists…');

    try {
        const resp = await fetch('/api/discover_artists', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ artist_count: artistCount, exploration }),
        });
        const data = await resp.json();
        if (!resp.ok || data.error) {
            showAlert(i18n('msg.error_prefix', 'Error: {detail}')
                .replace('{detail}', data.error || resp.status));
            return;
        }
        _artists = Array.isArray(data.artists) ? data.artists : [];
        renderDiscoveredArtists();
        if (_artists.length === 0) {
            showToast(i18n('artists.none',
                'No new artists found — try a different exploration setting.'));
        }
    } catch (e) {
        showAlert(i18n('msg.network_error', 'Network error: {detail}')
            .replace('{detail}', e.message));
    } finally {
        if (btn) btn.disabled = false;
        if (loadArea) loadArea.classList.add('hidden');
    }
}

export function renderDiscoveredArtists() {
    const list = el('discoverArtistsList');
    const area = el('discoverArtistsArea');
    if (!list) return;
    list.innerHTML = '';
    const has = _artists.length > 0;
    _setActionsVisible(has);
    if (area) area.classList.toggle('hidden', !has);
    if (!has) return;

    _artists.forEach(a => {
        const li = document.createElement('li');
        li.className = 'artist-discovery-item';
        const genres = (a.genres || [])
            .map(g => `<span class="artist-discovery-genre">${esc(g)}</span>`).join('');
        const tracks = (a.tracks || []).map(t => {
            const found = !!(t.found && t.uri);
            const cls = found
                ? 'artist-discovery-track'
                : 'artist-discovery-track artist-discovery-track--missing';
            const label = (found && t.spotify_url)
                ? `<a href="${esc(t.spotify_url)}" target="_blank" rel="noopener">${esc(t.track)}</a>`
                : esc(t.track);
            const tail = found
                ? ''
                : ` <span class="artist-discovery-missing">${esc(i18n('artists.track_missing', 'not on Spotify'))}</span>`;
            return `<li class="${cls}">${label}${tail}</li>`;
        }).join('');
        li.innerHTML = `
            <div class="artist-discovery-head">
                <span class="artist-discovery-name">${esc(a.artist)}</span>
                ${genres}
            </div>
            <div class="artist-discovery-reason">${esc(a.reason || '')}</div>
            <ul class="artist-discovery-tracks">${tracks}</ul>`;
        list.appendChild(li);
    });
}

export function clearDiscoveredArtists() {
    _artists = [];
    renderDiscoveredArtists();
    showToast(i18n('artists.cleared', 'Discovered artists cleared.'));
}

export function openArtistApplyModal() {
    const tracks = [];
    _artists.forEach(a => {
        (a.tracks || []).forEach(t => {
            if (t.found && t.uri) {
                tracks.push({
                    artist: t.artist || a.artist,
                    track: t.track,
                    uri: t.uri,
                    track_id: t.track_id,
                    cover_url: t.cover_url,
                });
            }
        });
    });
    if (tracks.length === 0) {
        showAlert(i18n('artists.no_applyable',
            'None of the discovered tracks were found on Spotify.'));
        return;
    }
    openApplyModal({ tracks, onApplied: clearDiscoveredArtists });
}

export function init() {
    const count = el('artistCount');
    const expl = el('artistExploration');
    if (count) count.addEventListener('input', _syncSliders);
    if (expl) expl.addEventListener('input', _syncSliders);
    _syncSliders();
}
