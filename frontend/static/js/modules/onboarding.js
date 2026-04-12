/* onboarding.js — Wizard state, navigation, language toggle, credential saving,
   Spotify connect, import, model picker, summary builder.
   Loaded as a regular <script> (not ES module) in onboarding.html. */

/* ── Lightweight i18n for onboarding ─────────────────────────── */
let _obStrings = {};

async function obSwitchLang(lang) {
    localStorage.setItem('svLang', lang);
    const langMap = { en: 'English', de: 'German' };
    const gptLang = langMap[lang];
    const payload = { ui_language: lang };
    if (gptLang) payload.gpt_language = gptLang;
    fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    }).catch(() => {});
    await obApplyLang(lang);
}

async function obApplyLang(lang) {
    try {
        const resp = await fetch(`/static/i18n/${lang}.json`);
        if (!resp.ok) return;
        _obStrings = await resp.json();
    } catch (e) { return; }

    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (_obStrings[key] !== undefined) {
            if (key === 'ob.credentials_explain' || key === 'af.hint_text') {
                el.innerHTML = _obStrings[key];
            } else {
                el.textContent = _obStrings[key];
            }
        }
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        if (_obStrings[key] !== undefined) el.placeholder = _obStrings[key];
    });
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const key = el.getAttribute('data-i18n-title');
        if (_obStrings[key] !== undefined) el.title = _obStrings[key];
    });

    // Sync all language toggle buttons
    document.querySelectorAll('.lang-toggle-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.lang === lang);
    });
}

function obI18n(key, fallback) {
    return _obStrings[key] !== undefined ? _obStrings[key] : (fallback || key);
}

/* ── Wizard navigation ───────────────────────────────────────── */
let currentPage = 0;
const totalPages = 7;

function obGoPage(idx) {
    if (idx < 0 || idx >= totalPages) return;
    currentPage = idx;
    document.getElementById('obPages').style.transform = `translateX(-${idx * 100}%)`;
    _updateIndicators();
    _updateNavButtons();

    // Mark pages for CSS/test targeting
    document.querySelectorAll('.ob-page').forEach((p, i) => {
        p.classList.toggle('active', i === idx);
    });

    // Step-specific activations
    if (idx === 5) obLoadModels();
    if (idx === 6) obBuildSummary();
}

function _updateIndicators() {
    document.querySelectorAll('.ob-pill').forEach((pill, i) => {
        pill.classList.remove('ob-pill--complete', 'ob-pill--current', 'ob-pill--future');
        if (i < currentPage) pill.classList.add('ob-pill--complete');
        else if (i === currentPage) pill.classList.add('ob-pill--current');
        else pill.classList.add('ob-pill--future');
    });
}

function _updateNavButtons() {
    // CTA (Next) enable/disable logic per step
    const cta = document.querySelector(`.ob-page:nth-child(${currentPage + 1}) .ob-cta-next`);
    if (cta) {
        if (currentPage === 1) {
            // Step 2: OpenAI key — enabled if input has content or key already set
            const hasKey = document.getElementById('ob-openai-key')?.value.trim();
            const isSet = !document.getElementById('ob-set-openai')?.classList.contains('hidden');
            cta.disabled = !(hasKey || isSet);
        } else if (currentPage === 2) {
            // Step 3: Spotify creds — both must have content or be already set
            const hasId = document.getElementById('ob-spotify-id')?.value.trim();
            const hasSecret = document.getElementById('ob-spotify-secret')?.value.trim();
            const idSet = !document.getElementById('ob-set-spotify-id')?.classList.contains('hidden');
            const secretSet = !document.getElementById('ob-set-spotify-secret')?.classList.contains('hidden');
            cta.disabled = !((hasId || idSet) && (hasSecret || secretSet));
        }
    }
}

// Touch/swipe support
let touchStartX = 0;
document.addEventListener('DOMContentLoaded', () => {
    const wrap = document.getElementById('obWrap');
    if (!wrap) return;
    wrap.addEventListener('touchstart', e => { touchStartX = e.touches[0].clientX; }, { passive: true });
    wrap.addEventListener('touchend', e => {
        const dx = e.changedTouches[0].clientX - touchStartX;
        if (dx < -50 && currentPage < totalPages - 1) obGoPage(currentPage + 1);
        if (dx > 50 && currentPage > 0) obGoPage(currentPage - 1);
    });

    // Enter key to advance
    wrap.addEventListener('keydown', e => {
        if (e.key === 'Enter' && e.target.tagName === 'INPUT') {
            const cta = document.querySelector(`.ob-page:nth-child(${currentPage + 1}) .ob-cta-next, .ob-page:nth-child(${currentPage + 1}) .ob-cta-start`);
            if (cta && !cta.disabled) cta.click();
        }
    });

    // Mark first page as active
    const firstPage = document.querySelector('.ob-page');
    if (firstPage) firstPage.classList.add('active');
});

/* ── Skip / Finish ────────────────────────────────────────────── */

async function skipOnboarding() {
    await _markComplete();
    window.location.href = '/';
}

async function finishOnboarding() {
    await _markComplete();
    window.location.href = '/';
}

async function _markComplete() {
    try {
        await fetch('/api/onboarding/complete', { method: 'POST' });
    } catch (e) { /* best-effort */ }
}

/* ── Credential saving (Steps 2 & 3) ─────────────────────────── */

async function obSaveAndNext() {
    if (currentPage === 1) {
        // Step 2: Save OpenAI key
        const key = document.getElementById('ob-openai-key')?.value.trim();
        if (key) {
            await _saveCredentials({ OPENAI_API_KEY: key });
            document.getElementById('ob-openai-key').value = '';
            await prefillCredentials();
        }
        obGoPage(2);
    } else if (currentPage === 2) {
        // Step 3: Save Spotify creds
        const id = document.getElementById('ob-spotify-id')?.value.trim();
        const secret = document.getElementById('ob-spotify-secret')?.value.trim();
        const payload = {};
        if (id) payload.SPOTIPY_CLIENT_ID = id;
        if (secret) payload.SPOTIPY_CLIENT_SECRET = secret;
        if (Object.keys(payload).length > 0) {
            await _saveCredentials(payload);
            if (id) document.getElementById('ob-spotify-id').value = '';
            if (secret) document.getElementById('ob-spotify-secret').value = '';
            await prefillCredentials();
        }
        obGoPage(3);
    } else if (currentPage === 5) {
        // Step 6: Save model
        const select = document.getElementById('ob-model-select');
        if (select && select.value) {
            try {
                await fetch('/api/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model: select.value }),
                });
            } catch (e) { /* best-effort */ }
        }
        obGoPage(6);
    } else {
        obGoPage(currentPage + 1);
    }
}

async function _saveCredentials(payload) {
    try {
        await fetch('/api/settings/credentials', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
    } catch (e) { /* best-effort */ }
}

const _obEditingFields = new Set();

function editObCredential(field) {
    const setRow = document.getElementById('ob-set-' + field);
    const inputWrap = document.getElementById('ob-input-wrap-' + field);
    if (setRow) setRow.classList.add('hidden');
    if (inputWrap) inputWrap.classList.remove('hidden');
    _obEditingFields.add(field);
    const inputMap = {
        'openai': 'ob-openai-key',
        'spotify-id': 'ob-spotify-id',
        'spotify-secret': 'ob-spotify-secret',
    };
    const inputEl = document.getElementById(inputMap[field]);
    if (inputEl) setTimeout(() => inputEl.focus(), 50);
    _updateNavButtons();
}

function onObCredentialInput() {
    _updateNavButtons();
}

/* ── Spotify connect (Step 4) ─────────────────────────────────── */

let _obSpotifyConnected = false;

function toggleObSpotify() {
    if (_obSpotifyConnected) {
        disconnectObSpotify();
    } else {
        connectObSpotify();
    }
}

function connectObSpotify() {
    const statusEl = document.getElementById('ob-spotify-status');
    if (statusEl) statusEl.textContent = obI18n('ob.opening_spotify', 'Opening Spotify…');
    if (/; wv\)/.test(navigator.userAgent)) {
        window.location.href = '/api/spotify/auth';
    } else {
        window.open('/api/spotify/auth', 'spotifyAuth', 'width=480,height=640');
        window.addEventListener('message', async (e) => {
            if (e.data === 'spotify-auth-complete') {
                _setObSpotifyState(true);
            }
        }, { once: true });
    }
}

async function disconnectObSpotify() {
    try {
        await fetch('/api/spotify/disconnect', { method: 'POST' });
        _setObSpotifyState(false);
    } catch (e) {
        const statusEl = document.getElementById('ob-spotify-status');
        if (statusEl) {
            statusEl.textContent = obI18n('ob.network_error', '❌ Network error.');
            statusEl.className = 'ob-explain ob-error';
        }
    }
}

function _setObSpotifyState(connected) {
    _obSpotifyConnected = connected;
    const btn = document.getElementById('ob-spotify-btn');
    const statusEl = document.getElementById('ob-spotify-status');
    if (connected) {
        if (btn) btn.textContent = obI18n('ob.disconnect_btn', '🔌 Disconnect from Spotify');
        if (statusEl) {
            statusEl.textContent = obI18n('ob.spotify_connected', '✅ Spotify connected!');
            statusEl.className = 'ob-explain ob-success';
        }
    } else {
        if (btn) btn.textContent = obI18n('ob.connect_btn', '🔌 Connect to Spotify');
        if (statusEl) {
            statusEl.textContent = '';
            statusEl.className = 'ob-explain';
        }
    }
}

async function _checkObSpotifyStatus() {
    try {
        const resp = await fetch('/api/spotify/status');
        const data = await resp.json();
        _setObSpotifyState(data.status === 'authenticated');
    } catch (e) { /* ignore */ }
}

/* ── Profile import (Step 5) ──────────────────────────────────── */

let _obProfileImported = false;

function obImportProfile() {
    const input = document.getElementById('ob-import-input');
    if (!input) return;
    input.value = '';
    input.onchange = async () => {
        const file = input.files[0];
        if (!file) return;
        const statusEl = document.getElementById('ob-import-status');
        try {
            const text = await file.text();
            const profile = JSON.parse(text);
            const resp = await fetch('/api/profile/import', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ profile }),
            });
            const data = await resp.json();
            if (resp.ok) {
                if (statusEl) {
                    statusEl.textContent = obI18n('ob.profile_imported', '✅ Profile imported.');
                    statusEl.className = 'ob-explain ob-success';
                }
                _obProfileImported = true;
            } else {
                if (statusEl) {
                    statusEl.textContent = '❌ ' + (data.error || obI18n('ob.import_failed', 'Import failed.'));
                    statusEl.className = 'ob-explain ob-error';
                }
            }
        } catch (e) {
            if (statusEl) {
                statusEl.textContent = '❌ ' + e.message;
                statusEl.className = 'ob-explain ob-error';
            }
        }
    };
    input.click();
}

/* ── How-do-I-get-this accordion ──────────────────────────────── */

function toggleObGuide(btnEl, bodyId) {
    const body = document.getElementById(bodyId);
    if (!body) return;
    const expanded = btnEl.getAttribute('aria-expanded') === 'true';
    btnEl.setAttribute('aria-expanded', String(!expanded));
    body.classList.toggle('open', !expanded);
}

/* ── Clipboard copy (Step 3 redirect URI) ─────────────────────── */

function obCopyRedirectUri(btn) {
    const uri = 'http://127.0.0.1:5000/callback';
    navigator.clipboard.writeText(uri).then(() => {
        const original = btn.textContent;
        btn.textContent = obI18n('ob.copied', '✓ Copied');
        setTimeout(() => { btn.textContent = original; }, 1500);
    }).catch(() => {
        // Fallback
        const ta = document.createElement('textarea');
        ta.value = uri;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        const original = btn.textContent;
        btn.textContent = obI18n('ob.copied', '✓ Copied');
        setTimeout(() => { btn.textContent = original; }, 1500);
    });
}

/* ── Model picker (Step 6) ────────────────────────────────────── */

let _obModelsLoaded = false;

async function obLoadModels() {
    if (_obModelsLoaded) return;
    const select = document.getElementById('ob-model-select');
    if (!select) return;
    try {
        const resp = await fetch('/api/settings');
        if (!resp.ok) return;
        const data = await resp.json();
        const models = data.available_models || [];
        const current = data.model || '';
        select.innerHTML = '';
        models.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m;
            opt.textContent = m;
            if (m === current) opt.selected = true;
            select.appendChild(opt);
        });
        _obModelsLoaded = true;
    } catch (e) { /* ignore */ }
}

/* ── Summary builder (Step 7) ─────────────────────────────────── */

async function obBuildSummary() {
    const rows = [
        { id: 'sum-openai', label: 'ob.sum_openai', fallback: 'OpenAI key' },
        { id: 'sum-spotify-cred', label: 'ob.sum_spotify_cred', fallback: 'Spotify developer app' },
        { id: 'sum-spotify-conn', label: 'ob.sum_spotify_conn', fallback: 'Spotify account' },
        { id: 'sum-profile', label: 'ob.sum_profile', fallback: 'Taste profile' },
        { id: 'sum-model', label: 'ob.sum_model', fallback: 'Model' },
    ];

    // Gather state
    let credData = {};
    try {
        const resp = await fetch('/api/settings/credentials');
        credData = await resp.json();
    } catch (e) {}

    let spotifyStatus = false;
    try {
        const resp = await fetch('/api/spotify/status');
        const data = await resp.json();
        spotifyStatus = data.status === 'authenticated';
        // Store display name if available
        if (data.display_name) {
            _obSpotifyDisplayName = data.display_name;
        }
    } catch (e) {}

    let profileTrained = false;
    try {
        const resp = await fetch('/api/profile/status');
        const data = await resp.json();
        profileTrained = data.trained === true;
    } catch (e) {}

    const checks = {
        'sum-openai': credData.OPENAI_API_KEY?.is_set === true,
        'sum-spotify-cred': credData.SPOTIPY_CLIENT_ID?.is_set === true && credData.SPOTIPY_CLIENT_SECRET?.is_set === true,
        'sum-spotify-conn': spotifyStatus,
        'sum-profile': profileTrained || _obProfileImported,
        'sum-model': true, // always has a default
    };

    const editTargets = {
        'sum-openai': 1,
        'sum-spotify-cred': 2,
        'sum-spotify-conn': 3,
        'sum-profile': 4,
        'sum-model': 5,
    };

    let hasSkipped = false;

    rows.forEach(row => {
        const el = document.getElementById(row.id);
        if (!el) return;

        const done = checks[row.id];
        if (!done) hasSkipped = true;

        const statusEl = el.querySelector('.ob-summary-status');
        const labelEl = el.querySelector('.ob-summary-label');
        const subEl = el.querySelector('.ob-summary-sub');
        const editBtn = el.querySelector('.ob-summary-edit');

        if (statusEl) {
            statusEl.className = 'ob-summary-status ' + (done ? 'ob-summary-status--done' : 'ob-summary-status--skipped');
            statusEl.textContent = done ? '✓' : '⚠';
        }

        if (labelEl) {
            labelEl.textContent = obI18n(row.label, row.fallback);
        }

        if (subEl) {
            if (done) {
                if (row.id === 'sum-spotify-conn' && _obSpotifyDisplayName) {
                    subEl.textContent = obI18n('ob.sum_connected_as', 'Connected as {user}').replace('{user}', _obSpotifyDisplayName);
                } else {
                    subEl.textContent = obI18n('ob.sum_set', 'Set');
                }
            } else {
                subEl.textContent = obI18n('ob.sum_not_set', 'Not set');
            }
        }

        if (editBtn) {
            const target = editTargets[row.id];
            editBtn.textContent = obI18n('ob.sum_edit', 'Edit');
            editBtn.onclick = () => obGoPage(target);
        }
    });

    // Skipped warning
    const warning = document.getElementById('ob-skipped-warning');
    if (warning) {
        warning.classList.toggle('hidden', !hasSkipped);
    }
}

let _obSpotifyDisplayName = '';

/* ── Credential prefill ───────────────────────────────────────── */

async function prefillCredentials() {
    try {
        const resp = await fetch('/api/settings/credentials');
        const data = await resp.json();

        const map = {
            'OPENAI_API_KEY':        { field: 'openai',         input: 'ob-openai-key',      i18nKey: 'ob.key_ok',     label: 'API Key' },
            'SPOTIPY_CLIENT_ID':     { field: 'spotify-id',     input: 'ob-spotify-id',      i18nKey: 'ob.id_ok',      label: 'Client ID' },
            'SPOTIPY_CLIENT_SECRET': { field: 'spotify-secret', input: 'ob-spotify-secret',  i18nKey: 'ob.secret_ok',  label: 'Client Secret' },
        };

        _obEditingFields.clear();

        for (const [key, ids] of Object.entries(map)) {
            const info = data[key];
            const setRow = document.getElementById('ob-set-' + ids.field);
            const inputWrap = document.getElementById('ob-input-wrap-' + ids.field);
            const inputEl = document.getElementById(ids.input);
            const labelEl = setRow ? setRow.querySelector('.ob-cred-set-label') : null;

            if (info && info.is_set) {
                if (setRow) setRow.classList.remove('hidden');
                if (inputWrap) inputWrap.classList.add('hidden');
                if (labelEl) labelEl.textContent = obI18n(ids.i18nKey, ids.label + ' — OK');
                if (inputEl) inputEl.value = '';
            } else {
                if (setRow) setRow.classList.add('hidden');
                if (inputWrap) inputWrap.classList.remove('hidden');
            }
        }

        _updateNavButtons();
    } catch (e) { /* ignore */ }
}

/* ── Init ─────────────────────────────────────────────────────── */

(async function() {
    // Check onboarding status (redirect if completed and not replay)
    const isReplay = new URLSearchParams(location.search).get('replay') === '1';
    try {
        const resp = await fetch('/api/onboarding/status');
        const data = await resp.json();
        if (data.completed && !isReplay) {
            window.location.href = '/';
            return;
        }
    } catch (e) { /* stay on page */ }

    // Determine language
    let lang = null;
    try {
        const resp = await fetch('/api/settings');
        if (resp.ok) {
            const settings = await resp.json();
            if (settings.ui_language) lang = settings.ui_language;
        }
    } catch { /* ignore */ }
    if (!lang) lang = localStorage.getItem('svLang');
    if (!lang) {
        const browserLang = (navigator.language || '').split('-')[0].toLowerCase();
        lang = (browserLang === 'de') ? 'de' : 'en';
    }
    localStorage.setItem('svLang', lang);
    await obApplyLang(lang);

    await prefillCredentials();
    await _checkObSpotifyStatus();
    _updateIndicators();
})();

