/**
 * playlist_seed.js — Seed profile from a Spotify playlist (Wave 3 C.1)
 */
import { i18n } from './i18n.js';
import { showToast } from './ui.js';
import { el } from './dom.js';

let _selectedPlaylistId = null;
let _currentSource = 'profile';
let _hasExistingProfile = false;

/**
 * Open the playlist seed picker modal.
 * @param {string} source - 'onboarding' or 'profile'
 */
export async function openPlaylistSeedPicker(source) {
    const modal = el('playlistSeedModal');
    if (!modal) return;
    modal.classList.add('open');
    _selectedPlaylistId = null;
    _currentSource = source || 'profile';

    const list = el('playlistSeedList');
    const loader = document.querySelector('.playlist-seed-loader');
    const loadingIndicator = document.querySelector('.playlist-seed-loading');
    const confirmBtn = el('playlistSeedConfirmBtn');
    const warn = document.querySelector('.playlist-seed-replace-warn');
    const searchRow = document.querySelector('.playlist-seed-search-row');

    if (list) list.innerHTML = '';
    if (loader) loader.classList.add('hidden');
    if (confirmBtn) confirmBtn.disabled = true;
    if (warn) warn.classList.add('hidden');

    // Show loading spinner while fetching playlists
    if (loadingIndicator) loadingIndicator.classList.remove('hidden');
    if (list) list.classList.add('hidden');
    if (searchRow) searchRow.classList.add('hidden');

    // Check if profile is non-empty to show replace warning on selection
    _hasExistingProfile = false;
    try {
        const profileResp = await fetch('/api/profile/status');
        if (profileResp.ok) {
            const profileData = await profileResp.json();
            _hasExistingProfile = profileData.trained === true;
        }
    } catch { /* ignore */ }

    // Fetch playlists
    try {
        const resp = await fetch('/api/spotify/playlists_for_seed');
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.error || 'Failed to fetch playlists');
        }
        const data = await resp.json();
        if (loadingIndicator) loadingIndicator.classList.add('hidden');
        if (list) list.classList.remove('hidden');
        if (searchRow) searchRow.classList.remove('hidden');
        _renderPlaylistList(data.playlists || [], source);
    } catch (e) {
        if (loadingIndicator) loadingIndicator.classList.add('hidden');
        if (list) list.classList.remove('hidden');
        if (searchRow) searchRow.classList.add('hidden');
        if (list) list.innerHTML = `<li class="playlist-seed-empty">
            <p style="color:var(--error)">${i18n('seed.failed', 'Could not load playlists.')}</p>
            <button class="btn-outline playlist-seed-retry" onclick="openPlaylistSeedPicker('${_esc(source || 'profile')}')">${i18n('seed.retry', 'Retry')}</button>
        </li>`;
    }
}

function _renderPlaylistList(playlists, source) {
    const list = el('playlistSeedList');
    if (!list) return;

    list.innerHTML = '';

    if (playlists.length === 0) {
        list.innerHTML = `<li class="playlist-seed-empty">
            <p>${i18n('seed.no_playlists', 'No playlists found on your Spotify account.')}</p>
            <button class="btn-outline playlist-seed-retry" onclick="openPlaylistSeedPicker('${_esc(source || _currentSource)}')">${i18n('seed.retry', 'Retry')}</button>
        </li>`;
        return;
    }

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
    const confirmBtn = el('playlistSeedConfirmBtn');
    if (confirmBtn) confirmBtn.disabled = false;
    // Show replace warning if profile is non-empty
    const warn = document.querySelector('.playlist-seed-replace-warn');
    if (warn) warn.classList.toggle('hidden', !_hasExistingProfile);
}

/**
 * Confirm the playlist selection and trigger profile draft.
 */
export async function confirmPlaylistSeed() {
    if (!_selectedPlaylistId) return;

    const list = el('playlistSeedList');
    const loader = document.querySelector('.playlist-seed-loader');
    const confirmBtn = el('playlistSeedConfirmBtn');

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
            // Advance to summary step if onboarding wizard function exists
            if (typeof window.obGoPage === 'function') {
                window.obGoPage(6);
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
    const coreDesc = el('trainCoreDesc');
    const mustHave = el('trainMustHave');
    const softPrefs = el('trainSoftPrefs');
    const avoid = el('trainAvoid');
    const vibeDesc = el('trainVibeDesc');

    if (coreDesc) coreDesc.value = draft.core_description || '';
    if (mustHave) mustHave.value = (draft.must_have || []).join('\n');
    if (softPrefs) softPrefs.value = (draft.soft_preferences || []).join('\n');
    if (avoid) avoid.value = (draft.avoid || []).join('\n');
    if (vibeDesc) vibeDesc.value = draft.vibe_description || '';

    // Dispatch input events so completeness meter recalculates
    [coreDesc, mustHave, softPrefs, avoid, vibeDesc].forEach(el => {
        if (el) el.dispatchEvent(new Event('input', { bubbles: true }));
    });

    // Show draft banner
    const banner = el('profileDraftBanner');
    if (banner) {
        banner.classList.remove('hidden');
        const sub = el('profileDraftSub');
        if (sub) {
            sub.textContent = i18n('profile.draft_sub_tpl', 'Generated from "{name}" — review and save below.')
                .replace('{name}', meta.playlist_name || '');
        }
    }

    // Expand the profile editor if collapsed
    const trainBody = el('trainBody');
    if (trainBody && trainBody.classList.contains('hidden')) {
        const toggleBtn = el('trainToggleBtn');
        if (toggleBtn) toggleBtn.click();
    }

    // Store draft metadata for save
    window._svDraftMeta = meta;
}

/**
 * Discard the current draft and reload the original profile.
 */
export async function discardProfileDraft() {
    const banner = el('profileDraftBanner');
    if (banner) banner.classList.add('hidden');
    window._svDraftMeta = null;

    // Reload pristine profile
    try {
        const resp = await fetch('/api/profile');
        if (resp.ok) {
            const data = await resp.json();
            const prefs = data.preferences || {};
            const coreDesc = el('trainCoreDesc');
            const mustHave = el('trainMustHave');
            const softPrefs = el('trainSoftPrefs');
            const avoid = el('trainAvoid');
            const vibeDesc = el('trainVibeDesc');

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
    const modal = el('playlistSeedModal');
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
    const search = el('playlistSeedSearch');
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



