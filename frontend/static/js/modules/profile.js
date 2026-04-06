import * as State from './state.js';
import { showToast, showAlert, showConfirm } from './ui.js';
import { i18n } from './i18n.js';

const TRAINING_TEXTS = {
    en: [
        'Teaching the AI your vibe…',
        'Analyzing your music taste…',
        'Consulting the algorithmic DJ…',
        'Cross-referencing with 80 million tracks…',
        'Deciding if pineapple belongs on pizza…',
        'Fine-tuning the recommendation engine…',
        'Almost there… probably…',
        'Your profile is getting a makeover…',
    ],
    de: [
        'Bringe der KI deinen Vibe bei…',
        'Analysiere deinen Musikgeschmack…',
        'Befrage den algorithmischen DJ…',
        'Vergleiche mit 80 Millionen Tracks…',
        'Entscheide, ob Ananas auf Pizza gehört…',
        'Feinabstimmung der Empfehlungsmaschine…',
        'Fast fertig… wahrscheinlich…',
        'Dein Profil bekommt ein Makeover…',
    ],
};


// ── Multi-profile management ────────────────────────────────────────

let _profileList = [];
let _activeProfileId = '';

/* ── Profile context menu (⋯ dropdown) ───────────────────────────── */

export function toggleProfileMenu() {
    const trigger = document.getElementById('profileMenuTrigger');
    const menu = document.getElementById('profileMenuDropdown');
    if (!trigger || !menu) return;

    const isOpen = !menu.classList.contains('hidden');
    if (isOpen) {
        _closeProfileMenu();
    } else {
        updateProfileMenuState();
        menu.classList.remove('hidden');
        trigger.setAttribute('aria-expanded', 'true');
        // Focus the first enabled menu item
        const firstEnabled = menu.querySelector('li:not(.disabled)');
        if (firstEnabled) firstEnabled.focus();
    }
}

function _closeProfileMenu() {
    const trigger = document.getElementById('profileMenuTrigger');
    const menu = document.getElementById('profileMenuDropdown');
    if (!trigger || !menu) return;
    menu.classList.add('hidden');
    trigger.setAttribute('aria-expanded', 'false');
}

export function initProfileMenu() {
    // Close menu on outside click
    document.addEventListener('click', (e) => {
        const wrapper = document.querySelector('.profile-menu-wrapper');
        if (wrapper && !wrapper.contains(e.target)) {
            _closeProfileMenu();
        }
    });

    // Keyboard navigation inside menu
    const menu = document.getElementById('profileMenuDropdown');
    if (menu) {
        menu.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                _closeProfileMenu();
                document.getElementById('profileMenuTrigger')?.focus();
            } else if (e.key === 'ArrowDown') {
                e.preventDefault();
                const items = [...menu.querySelectorAll('li:not(.disabled)')];
                const idx = items.indexOf(document.activeElement);
                const next = items[idx + 1] || items[0];
                if (next) next.focus();
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                const items = [...menu.querySelectorAll('li:not(.disabled)')];
                const idx = items.indexOf(document.activeElement);
                const prev = items[idx - 1] || items[items.length - 1];
                if (prev) prev.focus();
            }
        });
    }
}

export function updateProfileMenuState() {
    const hasProfile = Boolean(_activeProfileId);
    const ids = ['profileMenuExport', 'profileMenuReset', 'profileMenuDelete'];
    for (const id of ids) {
        const el = document.getElementById(id);
        if (!el) continue;
        if (hasProfile) {
            el.classList.remove('disabled');
            el.removeAttribute('aria-disabled');
        } else {
            el.classList.add('disabled');
            el.setAttribute('aria-disabled', 'true');
        }
    }
}

export async function loadProfileList() {
    try {
        const resp = await fetch('/api/profiles');
        const data = await resp.json();
        _profileList = data.profiles || [];
        _activeProfileId = data.active_id || '';
        _renderProfileDropdown();
    } catch (e) { /* ignore */ }
}

function _renderProfileDropdown() {
    const select = document.getElementById('profileSelect');
    if (!select) return;

    select.innerHTML = '';

    if (_profileList.length === 0) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = i18n('profile.no_profile_selected', 'No profile selected');
        select.appendChild(opt);
        _renderCustomDropdown();
        updateProfileMenuState();
        return;
    }

    for (const p of _profileList) {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = p.name || p.id;
        if (p.id === _activeProfileId) opt.selected = true;
        select.appendChild(opt);
    }

    _renderCustomDropdown();
    updateProfileMenuState();
}

/* ── Custom dropdown rendering & interaction ─────────────────────── */

function _renderCustomDropdown() {
    const label = document.getElementById('profileDropdownLabel');
    const list = document.getElementById('profileDropdownList');
    if (!label || !list) return;

    // Update label to show the active profile
    const active = _profileList.find(p => p.id === _activeProfileId);
    label.textContent = active
        ? (active.name || active.id)
        : i18n('profile.no_profile_selected', 'No profile selected');

    // Build list items
    list.innerHTML = '';
    if (_profileList.length === 0) {
        const li = document.createElement('li');
        li.textContent = i18n('profile.no_profile_selected', 'No profile selected');
        li.style.color = 'var(--text-muted)';
        li.style.cursor = 'default';
        list.appendChild(li);
        return;
    }

    for (const p of _profileList) {
        const li = document.createElement('li');
        li.setAttribute('role', 'option');
        li.setAttribute('data-value', p.id);
        li.setAttribute('tabindex', '-1');
        li.textContent = p.name || p.id;
        if (p.id === _activeProfileId) {
            li.setAttribute('aria-selected', 'true');
        }
        li.addEventListener('click', (e) => {
            e.stopPropagation();
            _selectCustomDropdownItem(p.id);
        });
        li.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                _selectCustomDropdownItem(p.id);
            } else if (e.key === 'ArrowDown') {
                e.preventDefault();
                const next = li.nextElementSibling;
                if (next) next.focus();
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                const prev = li.previousElementSibling;
                if (prev) prev.focus();
            } else if (e.key === 'Escape') {
                _closeCustomDropdown();
            }
        });
        list.appendChild(li);
    }
}

function _selectCustomDropdownItem(profileId) {
    // Update the hidden native select
    const select = document.getElementById('profileSelect');
    if (select) select.value = profileId;
    _closeCustomDropdown();
    switchProfile(profileId);
}

function _toggleCustomDropdown() {
    const dropdown = document.getElementById('profileCustomDropdown');
    const list = document.getElementById('profileDropdownList');
    if (!dropdown || !list) return;

    const isOpen = !list.classList.contains('hidden');
    if (isOpen) {
        _closeCustomDropdown();
    } else {
        list.classList.remove('hidden');
        dropdown.setAttribute('aria-expanded', 'true');
        // Focus the selected item or first item
        const selected = list.querySelector('[aria-selected="true"]') || list.querySelector('li');
        if (selected) selected.focus();
    }
}

function _closeCustomDropdown() {
    const dropdown = document.getElementById('profileCustomDropdown');
    const list = document.getElementById('profileDropdownList');
    if (!dropdown || !list) return;
    list.classList.add('hidden');
    dropdown.setAttribute('aria-expanded', 'false');
}

export function initCustomProfileDropdown() {
    const dropdown = document.getElementById('profileCustomDropdown');
    if (!dropdown) return;

    dropdown.addEventListener('click', (e) => {
        e.stopPropagation();
        _toggleCustomDropdown();
    });
    dropdown.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') {
            e.preventDefault();
            _toggleCustomDropdown();
        } else if (e.key === 'Escape') {
            _closeCustomDropdown();
        }
    });

    // Close on outside click
    document.addEventListener('click', () => {
        _closeCustomDropdown();
    });
}

export async function switchProfile(profileId) {
    if (!profileId || profileId === _activeProfileId) return;
    try {
        const resp = await fetch(`/api/profiles/${encodeURIComponent(profileId)}/activate`, { method: 'POST' });
        if (!resp.ok) {
            const data = await resp.json();
            showToast(data.error || 'Failed to switch profile.', 'error');
            return;
        }
        _activeProfileId = profileId;
        _renderCustomDropdown();
        await Promise.all([checkProfileStatus(), prefillTrainFields()]);
        showToast(i18n('msg.profile_switched', 'Profile switched.'), 'success');
    } catch (e) {
        showToast('Network error: ' + e.message, 'error');
    }
}

export function toggleCreateProfile() {
    const wrap = document.getElementById('profileCreateWrap');
    const toggle = document.getElementById('profileCreateToggle');
    const input = document.getElementById('profileCreateInput');
    const error = document.getElementById('profileCreateError');

    if (wrap.classList.contains('hidden')) {
        wrap.classList.remove('hidden');
        toggle.classList.add('hidden');
        error.classList.add('hidden');
        input.value = '';
        input.focus();
        toggle.setAttribute('aria-expanded', 'true');
    } else {
        wrap.classList.add('hidden');
        toggle.classList.remove('hidden');
        error.classList.add('hidden');
        toggle.setAttribute('aria-expanded', 'false');
    }
}

export async function createNewProfile() {
    const input = document.getElementById('profileCreateInput');
    const error = document.getElementById('profileCreateError');
    const name = (input.value || '').trim();

    if (!name) {
        error.textContent = i18n('profile.name_required', 'Enter a profile name.');
        error.classList.remove('hidden');
        input.focus();
        return;
    }

    try {
        const resp = await fetch('/api/profiles', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name }),
        });
        const data = await resp.json();

        if (!resp.ok || data.error) {
            error.textContent = data.error || 'Failed to create profile.';
            error.classList.remove('hidden');
            input.focus();
            return;
        }

        // Collapse the create input
        toggleCreateProfile();

        // Reload the profile list — the new profile is auto-activated
        await loadProfileList();
        await Promise.all([checkProfileStatus(), prefillTrainFields()]);
        showToast(i18n('msg.profile_created', 'Profile created.'), 'success');
    } catch (e) {
        error.textContent = 'Network error: ' + e.message;
        error.classList.remove('hidden');
    }
}

export async function deleteCurrentProfile() {
    if (!_activeProfileId) return;

    const currentName = _profileList.find(p => p.id === _activeProfileId)?.name || 'this profile';
    const ok = await showConfirm(
        `Delete "${currentName}"?\n\nThis cannot be undone.`
    );
    if (!ok) return;

    try {
        const resp = await fetch(`/api/profiles/${encodeURIComponent(_activeProfileId)}`, { method: 'DELETE' });
        const data = await resp.json();

        if (!resp.ok || data.error) {
            showToast(data.error || 'Delete failed.', 'error');
            return;
        }

        _activeProfileId = '';
        await loadProfileList();

        // Auto-select the first remaining profile if any
        if (_profileList.length > 0) {
            await switchProfile(_profileList[0].id);
        } else {
            await checkProfileStatus();
            _clearTrainFields();
        }

        showToast(i18n('msg.profile_deleted', 'Profile deleted.'), 'success');
    } catch (e) {
        showToast('Network error: ' + e.message, 'error');
    }
}

function _clearTrainFields() {
    const ids = ['trainVibeDesc', 'trainCoreDesc', 'trainMustHave', 'trainSoftPrefs', 'trainAvoid'];
    for (const id of ids) {
        const el = document.getElementById(id);
        if (el) el.value = '';
    }
}


// ── Existing profile functions ──────────────────────────────────────

export function toggleAccordion(id) {
    const panel = document.getElementById(id);
    panel.classList.toggle('open');
    const header = panel.querySelector('.accordion-header');
    if (header) header.setAttribute('aria-expanded', panel.classList.contains('open'));
}

export async function checkProfileStatus() {
    try {
        const resp = await fetch('/api/profile/status');
        const data = await resp.json();

        if (data.no_profile) {
            State.setProfileTrained(false);
            const el = document.getElementById('trainStatus');
            if (el) el.textContent = i18n('profile.no_profile_hint', 'Create a profile to get started.');
            return;
        }

        State.setProfileTrained(data.trained);
        const el = document.getElementById('trainStatus');
        if (data.trained) {
            const d = new Date(data.last_updated);
            el.textContent = '✓ Last trained: ' + d.toLocaleString();
        } else {
            el.textContent = '⚠ Not yet trained — describe your taste below.';
            document.getElementById('trainBody').classList.remove('hidden');
            State.setUserProfileEditMode(true);
            updateTrainToggleLabel();
            prefillTrainFields();
        }
    } catch (e) { /* ignore */ }
}

export async function prefillTrainFields() {
    try {
        const resp = await fetch('/api/profile/data');
        if (!resp.ok) return;
        const profile = await resp.json();
        const prefs = profile.preferences || {};

        document.getElementById('trainVibeDesc').value = prefs.vibe_description || '';
        document.getElementById('trainCoreDesc').value = prefs.core_description || '';
        document.getElementById('trainMustHave').value = (prefs.must_have || []).join('\n');
        document.getElementById('trainSoftPrefs').value = (prefs.soft_preferences || []).join('\n');
        document.getElementById('trainAvoid').value = (prefs.avoid || []).join('\n');
    } catch (e) { /* ignore — fields stay empty */ }
}

function _hideAiWarning() {
    const warning = document.getElementById('trainAiWarning');
    if (warning) warning.classList.add('hidden');
}

export function updateTrainToggleLabel() {
    const body = document.getElementById('trainBody');
    const btn = document.getElementById('trainToggleBtn');
    if (!body || !btn) return;
    btn.textContent = body.classList.contains('hidden') ? i18n('btn.show', 'Show') : i18n('btn.hide', 'Hide');
}

export function toggleTrainBody() {
    const body = document.getElementById('trainBody');
    const isOpening = body.classList.contains('hidden');

    if (isOpening) {
        body.classList.remove('hidden');
        State.setUserProfileEditMode(true);
        prefillTrainFields();
    } else {
        body.classList.add('hidden');
        State.setUserProfileEditMode(false);
    }

    updateTrainToggleLabel();

    // Sync aria-expanded on the section header and toggle button
    const expanded = isOpening.toString();
    const header = document.querySelector('#trainSection > .train-header');
    if (header) header.setAttribute('aria-expanded', expanded);
    const btn = document.getElementById('trainToggleBtn');
    if (btn) btn.setAttribute('aria-expanded', expanded);
}

export async function startImportProfile() {
    const input = document.getElementById('profileImportInput');
    if (!input) return;

    const ok = await showConfirm(
        'Import profile? This will replace your current profile file.\n\n' +
        'Your previous profile will be backed up automatically to the history file.'
    );
    if (!ok) return;

    input.value = '';
    input.click();
}

export async function exportProfile() {
    try {
        const a = document.createElement('a');
        a.href = '/api/profile/export';
        a.download = 'spotyvibe_profile.json';
        document.body.appendChild(a);
        a.click();
        a.remove();
        showToast(i18n('msg.export_saved', 'Profile exported — check your Downloads folder for spotyvibe_profile.json'), 'success', 5000);
    } catch (e) {
        window.location.href = '/api/profile/export';
    }
}

async function handleProfileImportFile(file) {
    if (!file) return;

    const MAX_IMPORT_BYTES = 10 * 1024 * 1024;
    if (file.size > MAX_IMPORT_BYTES) {
        showToast('Import failed: file is larger than 10MB.', 'error');
        return;
    }

    const text = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ''));
        reader.onerror = () => reject(new Error('Could not read file'));
        reader.readAsText(file);
    });

    let parsed;
    try {
        parsed = JSON.parse(text);
    } catch (e) {
        showToast('Invalid JSON file.', 'error');
        return;
    }

    try {
        const resp = await fetch('/api/profile/import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile: parsed }),
        });
        const data = await resp.json();

        if (!resp.ok || data.error) {
            showToast('Import failed: ' + (data.error || 'unknown error'), 'error');
            return;
        }

        showToast('Profile imported. Previous profile saved to history.', 'success');
        await Promise.all([checkProfileStatus(), prefillTrainFields()]);
    } catch (e) {
        showToast('Network error: ' + e.message, 'error');
    }
}

export function bindProfileImportInput() {
    const input = document.getElementById('profileImportInput');
    if (!input) return;
    input.addEventListener('change', () => {
        const file = input.files && input.files[0];
        handleProfileImportFile(file);
    });
}

export async function submitProfile(endpoint, btnId, btnLabel, loadingLabel, successMsg, requireOpenAI) {
    if (requireOpenAI && !State.openaiKeySet) {
        showToast('OpenAI API key is required. Open ⚙️ Settings.', 'error');
        return;
    }

    const vibeDesc = document.getElementById('trainVibeDesc').value.trim();
    const coreDesc = document.getElementById('trainCoreDesc').value.trim();

    // For AI training, require at least one description
    if (requireOpenAI && !coreDesc && !vibeDesc) {
        const warning = document.getElementById('trainAiWarning');
        if (warning) warning.classList.remove('hidden');
        return;
    }
    _hideAiWarning();

    const mustHave = document.getElementById('trainMustHave').value.trim();
    const softPrefs = document.getElementById('trainSoftPrefs').value.trim();
    const avoid = document.getElementById('trainAvoid').value.trim();

    const btn = document.getElementById(btnId);
    btn.disabled = true;
    btn.textContent = loadingLabel;

    let textInterval;
    if (endpoint === '/api/train-profile') {
        const spinner = document.getElementById('trainSpinner');
        const spinnerText = document.getElementById('trainSpinnerText');
        spinner.classList.remove('hidden');
        const lang = localStorage.getItem('svLang') || 'en';
        const texts = TRAINING_TEXTS[lang] || TRAINING_TEXTS.en;
        let textIdx = 0;
        spinnerText.textContent = texts[0];
        textInterval = setInterval(() => {
            textIdx = (textIdx + 1) % texts.length;
            spinnerText.textContent = texts[textIdx];
        }, 3000);
    }

    try {
        const resp = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                vibe_description: vibeDesc,
                core_description: coreDesc,
                must_have: mustHave,
                soft_preferences: softPrefs,
                avoid: avoid,
            }),
        });
        const data = await resp.json();

        if (!resp.ok || data.error) {
            showAlert('Error: ' + (data.error || 'unknown'));
            return;
        }

        document.getElementById('trainBody').classList.add('hidden');
        State.setUserProfileEditMode(false);
        updateTrainToggleLabel();

        const icon = document.getElementById('trainSuccessIcon');
        icon.className = 'train-success';
        icon.textContent = successMsg;
        icon.classList.remove('hidden');
        setTimeout(() => { icon.classList.add('hidden'); }, 5000);

        await checkProfileStatus();

    } catch (e) {
        showAlert('Network error: ' + e.message);
    } finally {
        if (textInterval) clearInterval(textInterval);
        document.getElementById('trainSpinner')?.classList.add('hidden');
        btn.disabled = false;
        btn.textContent = btnLabel;
    }
}

export function sendTrainProfile() {
    return submitProfile('/api/train-profile', 'trainSendBtn', 'AI Profile Update', '⏳ Training…', '✅ Profile updated!', true);
}

export function saveProfileDirect() {
    return submitProfile('/api/save-profile', 'trainSaveBtn', 'Save', '⏳ Saving…', '✅ Profile saved!', false);
}

export async function resetProfileToHistory() {
    const ok = await showConfirm(
        'Reset profile to history?\n\n' +
        'This swaps your current profile with the previous saved version.'
    );
    if (!ok) return;

    try {
        const resp = await fetch('/api/profile/reset-to-history', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        });
        const data = await resp.json();

        if (!resp.ok || data.error) {
            showToast('Reset failed: ' + (data.error || 'unknown error'), 'error');
            return;
        }

        showToast('Profile reset to history.', 'success');
        await Promise.all([checkProfileStatus(), prefillTrainFields()]);
    } catch (e) {
        showToast('Network error: ' + e.message, 'error');
    }
}
