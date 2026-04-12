/**
 * playlist_seed.js — Seed profile from a Spotify playlist (Wave 3 C.1)
 */
import { i18n } from './i18n.js';
import { showToast } from './ui.js';

let _selectedPlaylistId = null;
let _currentSource = 'profile';

/**
 * Open the playlist seed picker modal.
 * @param {string} source - 'onboarding' or 'profile'
 */
export async function openPlaylistSeedPicker(source) {
    const modal = document.getElementById('playlistSeedModal');
    if (!modal) return;
    modal.classList.add('open');
    _selectedPlaylistId = null;
    _currentSource = source || 'profile';

    const list = document.getElementById('playlistSeedList');
    const loader = document.querySelector('.playlist-seed-loader');
    const confirmBtn = document.getElementById('playlistSeedConfirmBtn');
    const warn = document.querySelector('.playlist-seed-replace-warn');

    if (list) list.innerHTML = '';
    if (loader) loader.classList.add('hidden');
    if (confirmBtn) confirmBtn.disabled = true;
    if (warn) warn.classList.add('hidden');

    // Fetch playlists
    try {
        const resp = await fetch('/api/spotify/playlists_for_seed');
        if (!resp.ok) throw new Error('Failed to fetch playlists');
        const data = await resp.json();
        _renderPlaylistList(data.playlists || [], source);
    } catch (e) {
        if (list) list.innerHTML = `<p style="color:var(--error);padding:12px">${i18n('seed.failed', 'Could not load playlists.')}</p>`;
    }
}

function _renderPlaylistList(playlists, source) {
    const list = document.getElementById('playlistSeedList');
    if (!list) return;

    list.innerHTML = '';
    playlists.forEach(p => {
        const li = document.createElement('li');
        li.className = 'playlist-seed-item';
        li.dataset.playlistId = p.id;
        li.innerHTML = `
            ${p.cover_url ? `<img class="playlist-seed-cover" src="${p.cover_url}" alt="" loading="lazy">` : '<div class="playlist-seed-cover"></div>'}
            <div class="playlist-seed-text">
                <div class="playlist-seed-name">${_esc(p.name)}</div>
                <div class="playlist-seed-meta">${i18n('seed.track_count', '{count} tracks').replace('{count}', p.track_count)} · ${i18n('seed.owner', 'by {owner}').replace('{owner}', _esc(p.owner))}</div>
            </div>
            <div class="playlist-seed-check"></div>
        `;
        li.addEventListener('click', () => _selectPlaylist(li, p.id));
        list.appendChild(li);
    });
}

function _selectPlaylist(li, playlistId) {
    document.querySelectorAll('.playlist-seed-item.selected').forEach(el => el.classList.remove('selected'));
    li.classList.add('selected');
    _selectedPlaylistId = playlistId;
    const confirmBtn = document.getElementById('playlistSeedConfirmBtn');
    if (confirmBtn) confirmBtn.disabled = false;
}

/**
 * Confirm the playlist selection and trigger profile draft.
 */
export async function confirmPlaylistSeed() {
    if (!_selectedPlaylistId) return;

    const list = document.getElementById('playlistSeedList');
    const loader = document.querySelector('.playlist-seed-loader');
    const confirmBtn = document.getElementById('playlistSeedConfirmBtn');

    if (list) list.classList.add('hidden');
    if (loader) loader.classList.remove('hidden');
    if (confirmBtn) confirmBtn.disabled = true;

    try {
        const resp = await fetch('/api/profile/seed_from_playlist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ playlist_id: _selectedPlaylistId }),
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || 'Draft failed');
        }

        const data = await resp.json();
        _closeModal();

        if (_currentSource === 'onboarding') {
            // Stash draft for next page load
            sessionStorage.setItem('sv.draft_profile', JSON.stringify({
                draft: data.draft,
                meta: data.meta,
            }));
            // Advance to step 6 if onboarding wizard function exists
            if (typeof window.obGoPage === 'function') {
                window.obGoPage(5);
            }
        } else {
            _applyDraft(data.draft, data.meta);
        }
    } catch (e) {
        if (list) list.classList.remove('hidden');
        if (loader) loader.classList.add('hidden');
        showToast(i18n('seed.failed', "Couldn't draft a profile from this playlist. Please try a different one."));
    }
}

function _applyDraft(draft, meta) {
    // Fill profile editor fields
    const coreDesc = document.getElementById('trainCoreDesc');
    const mustHave = document.getElementById('trainMustHave');
    const softPrefs = document.getElementById('trainSoftPrefs');
    const avoid = document.getElementById('trainAvoid');
    const vibeDesc = document.getElementById('trainVibeDesc');

    if (coreDesc) coreDesc.value = draft.core_description || '';
    if (mustHave) mustHave.value = (draft.must_have || []).join('\n');
    if (softPrefs) softPrefs.value = (draft.soft_preferences || []).join('\n');
    if (avoid) avoid.value = (draft.avoid || []).join('\n');
    if (vibeDesc) vibeDesc.value = draft.vibe_description || '';

    // Show draft banner
    const banner = document.getElementById('profileDraftBanner');
    if (banner) {
        banner.classList.remove('hidden');
        const sub = document.getElementById('profileDraftSub');
        if (sub) {
            sub.textContent = i18n('profile.draft_sub_tpl', 'Generated from "{name}" — review and save below.')
                .replace('{name}', meta.playlist_name || '');
        }
    }

    // Expand the profile editor if collapsed
    const trainBody = document.getElementById('trainBody');
    if (trainBody && trainBody.classList.contains('hidden')) {
        const toggleBtn = document.getElementById('trainToggleBtn');
        if (toggleBtn) toggleBtn.click();
    }

    // Store draft metadata for save
    window._svDraftMeta = meta;
}

/**
 * Discard the current draft and reload the original profile.
 */
export async function discardProfileDraft() {
    const banner = document.getElementById('profileDraftBanner');
    if (banner) banner.classList.add('hidden');
    window._svDraftMeta = null;

    // Reload pristine profile
    try {
        const resp = await fetch('/api/profile');
        if (resp.ok) {
            const data = await resp.json();
            const prefs = data.preferences || {};
            const coreDesc = document.getElementById('trainCoreDesc');
            const mustHave = document.getElementById('trainMustHave');
            const softPrefs = document.getElementById('trainSoftPrefs');
            const avoid = document.getElementById('trainAvoid');
            const vibeDesc = document.getElementById('trainVibeDesc');

            if (coreDesc) coreDesc.value = prefs.core_description || '';
            if (mustHave) mustHave.value = (prefs.must_have || []).join('\n');
            if (softPrefs) softPrefs.value = (prefs.soft_preferences || []).join('\n');
            if (avoid) avoid.value = (prefs.avoid || []).join('\n');
            if (vibeDesc) vibeDesc.value = prefs.vibe_description || '';
        }
    } catch (e) {
        // Silently ignore
    }
}

function _closeModal() {
    const modal = document.getElementById('playlistSeedModal');
    if (modal) modal.classList.remove('open');
}

function _esc(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

/**
 * Apply a pending draft from sessionStorage (onboarding flow).
 */
export function applyPendingDraftIfAny() {
    try {
        const raw = sessionStorage.getItem('sv.draft_profile');
        if (!raw) return;
        sessionStorage.removeItem('sv.draft_profile');
        const { draft, meta } = JSON.parse(raw);
        _applyDraft(draft, meta);
    } catch (e) {
        // Silently ignore
    }
}

export function init() {
    window.openPlaylistSeedPicker = openPlaylistSeedPicker;
    window.confirmPlaylistSeed = confirmPlaylistSeed;
    window.discardProfileDraft = discardProfileDraft;

    // Search filtering
    const search = document.getElementById('playlistSeedSearch');
    if (search) {
        search.addEventListener('input', () => {
            const q = search.value.toLowerCase();
            document.querySelectorAll('.playlist-seed-item').forEach(li => {
                const name = li.querySelector('.playlist-seed-name');
                li.style.display = name && name.textContent.toLowerCase().includes(q) ? '' : 'none';
            });
        });
    }
}



