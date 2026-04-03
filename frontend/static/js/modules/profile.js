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
        return;
    }

    for (const p of _profileList) {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = p.name || p.id;
        if (p.id === _activeProfileId) opt.selected = true;
        select.appendChild(opt);
    }
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
            State.setUserProfileEditMode(false);
            updateProfileIoVisibility();
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
        _updateAiWarning();
    } catch (e) { /* ignore — fields stay empty */ }
}

function _updateAiWarning() {
    const vibeDesc = (document.getElementById('trainVibeDesc').value || '').trim();
    const coreDesc = (document.getElementById('trainCoreDesc').value || '').trim();
    const warning = document.getElementById('trainAiWarning');
    if (warning) {
        warning.classList.toggle('hidden', !!(vibeDesc || coreDesc));
    }
}

function updateProfileIoVisibility() {
    const io = document.getElementById('profileIoActions');
    if (!io) return;
    io.classList.toggle('hidden', !State.userProfileEditMode);
}

export function updateTrainToggleLabel() {
    const body = document.getElementById('trainBody');
    const btn = document.getElementById('trainToggleBtn');
    if (!body || !btn) return;
    btn.textContent = body.classList.contains('hidden') ? 'Edit profile' : 'Hide profile';
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

    updateProfileIoVisibility();
    updateTrainToggleLabel();

    // Show/hide the profile selector and status alongside the body
    const profileSel = document.getElementById('profileSelector');
    if (profileSel) profileSel.classList.toggle('hidden', !isOpening);
    const trainStatus = document.getElementById('trainStatus');
    if (trainStatus) trainStatus.classList.toggle('hidden', !isOpening);

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

    // Update AI warning when description fields change
    const vibeInput = document.getElementById('trainVibeDesc');
    const coreInput = document.getElementById('trainCoreDesc');
    if (vibeInput) vibeInput.addEventListener('input', _updateAiWarning);
    if (coreInput) coreInput.addEventListener('input', _updateAiWarning);
}

export async function submitProfile(endpoint, btnId, btnLabel, loadingLabel, successMsg, requireOpenAI) {
    if (requireOpenAI && !State.openaiKeySet) {
        showToast('OpenAI API key is required. Open ⚙️ Settings.', 'error');
        return;
    }

    const vibeDesc = document.getElementById('trainVibeDesc').value.trim();
    const coreDesc = document.getElementById('trainCoreDesc').value.trim();
    const coreInput = document.getElementById('trainCoreDesc');
    const errMsg = document.getElementById('errCoreDesc');

    // For AI training, require at least one description
    if (requireOpenAI && !coreDesc && !vibeDesc) {
        coreInput.classList.add('input-error');
        errMsg.style.display = 'block';
        document.getElementById('accCoreDesc').classList.add('open');
        coreInput.focus();
        return;
    }
    coreInput.classList.remove('input-error');
    errMsg.style.display = 'none';

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
        updateProfileIoVisibility();
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
