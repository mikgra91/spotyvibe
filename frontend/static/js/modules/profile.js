import * as State from './state.js';
import { showToast } from './ui.js';

export function toggleAccordion(id) {
    document.getElementById(id).classList.toggle('open');
}

export async function checkProfileStatus() {
    try {
        const resp = await fetch('/api/profile/status');
        const data = await resp.json();
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
        const profile = await resp.json();
        const prefs = profile.preferences || {};

        document.getElementById('trainCoreDesc').value = prefs.core_description || '';
        document.getElementById('trainMustHave').value = (prefs.must_have || []).join('\n');
        document.getElementById('trainSoftPrefs').value = (prefs.soft_preferences || []).join('\n');
        document.getElementById('trainAvoid').value = (prefs.avoid || []).join('\n');
    } catch (e) { /* ignore — fields stay empty */ }
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
}

export function startImportProfile() {
    const input = document.getElementById('profileImportInput');
    if (!input) return;

    const ok = confirm(
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
        showToast('Export started…', 'info', 2000);
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

    const coreDesc = document.getElementById('trainCoreDesc').value.trim();
    const coreInput = document.getElementById('trainCoreDesc');
    const errMsg = document.getElementById('errCoreDesc');

    if (!coreDesc) {
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

    try {
        const resp = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                core_description: coreDesc,
                must_have: mustHave,
                soft_preferences: softPrefs,
                avoid: avoid,
            }),
        });
        const data = await resp.json();

        if (!resp.ok || data.error) {
            alert('Error: ' + (data.error || 'unknown'));
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
        alert('Network error: ' + e.message);
    } finally {
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
    const ok = confirm(
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
