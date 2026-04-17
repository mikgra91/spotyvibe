/* onboarding.js — Wizard state, navigation, language toggle, credential saving,
   Spotify connect, import, model picker, summary builder.
   Loaded as a regular <script> (not ES module) in onboarding.html. */

const el = (id) => document.getElementById(id);

/* ── Lightweight i18n for onboarding ─────────────────────────── */
let _obStrings = {};

async function obSwitchLang(lang) {
    localStorage.setItem('svLang', lang);
    const langMap = { en: 'English', de: 'German', jp: 'Japanese' };
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

    // Refresh dynamically-set elements that don't use data-i18n
    const badge = el('obProviderBadge');
    if (badge && typeof _obSelectedProvider !== 'undefined') {
        const providerLabel = document.querySelector(`#ob-provider-list .ob-custom-select-option[data-value="${_obSelectedProvider}"]`);
        const providerName = providerLabel ? providerLabel.textContent.trim() : _obSelectedProvider;
        badge.textContent = obI18n('ob.step6_provider_note', 'You chose: {provider}').replace('{provider}', providerName);
    }
}

function obI18n(key, fallback) {
    return _obStrings[key] !== undefined ? _obStrings[key] : (fallback || key);
}

/* ── Wizard navigation ───────────────────────────────────────── */
let currentPage = 0;
const totalPages = 7;

/* ── B.5: In-session touch tracking for summary ──────────────── */
const obTouched = {
    openai_key: false,
    provider: false,
    spotify_cred: false,
    spotify_conn: false,
    profile: false,
    model: false,
};

/* ── B.1/B.4: Provider custom dropdown state ─────────────────── */
let _obSelectedProvider = 'openai';

/* ── AI readiness tracking (key set + model chosen) ──────────── */
let _obAiReady = false;

const _PROVIDER_META = {
    openai:     { local: false, label_i18n: 'provider.api_key_label_openai',     hint_i18n: 'provider.api_key_hint_openai',     placeholder: 'sk-…' },
    ollama:     { local: true,  label_i18n: 'provider.api_key_label_ollama',     hint_i18n: 'provider.api_key_hint_ollama',     placeholder: 'any value or leave empty' },
    lmstudio:   { local: true,  label_i18n: 'provider.api_key_label_lmstudio',   hint_i18n: 'provider.api_key_hint_lmstudio',   placeholder: 'any value or leave empty' },
    groq:       { local: false, label_i18n: 'provider.api_key_label_groq',       hint_i18n: 'provider.api_key_hint_groq',       placeholder: 'gsk_…' },
    openrouter: { local: false, label_i18n: 'provider.api_key_label_openrouter', hint_i18n: 'provider.api_key_hint_openrouter', placeholder: 'sk-or-…' },
};

const _PROVIDER_BASE_URLS = {
    openai:     'https://api.openai.com/v1',
    ollama:     'http://localhost:11434/v1',
    lmstudio:   'http://localhost:1234/v1',
    groq:       'https://api.groq.com/openai/v1',
    openrouter: 'https://openrouter.ai/api/v1',
    custom:     '',
};

function obGoPage(idx) {
    if (idx < 0 || idx >= totalPages) return;
    currentPage = idx;
    el('obPages').style.transform = `translateX(-${idx * 100}%)`;
    _updateIndicators();
    _updateNavButtons();

    // Mark pages for CSS/test targeting
    document.querySelectorAll('.ob-page').forEach((p, i) => {
        p.classList.toggle('active', i === idx);
    });

    // Step-specific activations
    if (idx === 4) {
        obLoadModels();
        _obInitCostWidget();
    }
    if (idx === 5) _updateSeedCardStates();
    if (idx === 6) obBuildSummary();
}

function _updateIndicators() {
    document.querySelectorAll('.ob-step-indicator').forEach(indicator => {
        indicator.querySelectorAll('.ob-pill').forEach((pill, i) => {
            pill.classList.remove('ob-pill--complete', 'ob-pill--current', 'ob-pill--future');
            if (i < currentPage) pill.classList.add('ob-pill--complete');
            else if (i === currentPage) pill.classList.add('ob-pill--current');
            else pill.classList.add('ob-pill--future');
        });
    });
}

function _updateNavButtons() {
    // CTA (Next) enable/disable logic per step
    const cta = document.querySelector(`.ob-page:nth-child(${currentPage + 1}) .ob-cta-next`);
    if (cta) {
        if (currentPage === 1) {
            // Step 2: OpenAI key — enabled if local provider, or input has content, or key already set
            const isLocal = (_PROVIDER_META[_obSelectedProvider] || {}).local === true;
            const hasKey = el('ob-openai-key')?.value.trim();
            const isSet = !el('ob-set-openai')?.classList.contains('hidden');
            cta.disabled = !(isLocal || hasKey || isSet);
        } else if (currentPage === 2) {
            // Step 3: Spotify creds — both must have content or be already set
            const hasId = el('ob-spotify-id')?.value.trim();
            const hasSecret = el('ob-spotify-secret')?.value.trim();
            const idSet = !el('ob-set-spotify-id')?.classList.contains('hidden');
            const secretSet = !el('ob-set-spotify-secret')?.classList.contains('hidden');
            cta.disabled = !((hasId || idSet) && (hasSecret || secretSet));
        }
    }
}

// Touch/swipe support
let touchStartX = 0;
document.addEventListener('DOMContentLoaded', () => {
    const wrap = el('obWrap');
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

    // ── B.1: Custom provider dropdown ──
    _initObProviderDropdown();
});

/* ── Skip / Finish ────────────────────────────────────────────── */

/* ── B.1: Custom provider dropdown logic ─────────────────────── */

function _initObProviderDropdown() {
    const dropdown = el('ob-provider-dropdown');
    const trigger = el('ob-provider-trigger');
    const list = el('ob-provider-list');
    if (!dropdown || !trigger || !list) return;

    // Toggle open/close
    trigger.addEventListener('click', () => {
        const open = dropdown.classList.toggle('open');
        trigger.setAttribute('aria-expanded', String(open));
        if (open) {
            // Focus the selected option
            const sel = list.querySelector('.selected');
            if (sel) sel.focus();
        }
    });

    // Option selection
    list.addEventListener('click', (e) => {
        const option = e.target.closest('.ob-custom-select-option');
        if (!option) return;
        _selectObProvider(option.dataset.value, option.textContent.trim());
        dropdown.classList.remove('open');
        trigger.setAttribute('aria-expanded', 'false');
        trigger.focus();
    });

    // Keyboard navigation
    list.addEventListener('keydown', (e) => {
        const options = [...list.querySelectorAll('.ob-custom-select-option')];
        const focused = document.activeElement;
        const idx = options.indexOf(focused);
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (idx < options.length - 1) options[idx + 1].focus();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (idx > 0) options[idx - 1].focus();
        } else if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            if (focused && focused.dataset.value) {
                _selectObProvider(focused.dataset.value, focused.textContent.trim());
                dropdown.classList.remove('open');
                trigger.setAttribute('aria-expanded', 'false');
                trigger.focus();
            }
        } else if (e.key === 'Escape') {
            dropdown.classList.remove('open');
            trigger.setAttribute('aria-expanded', 'false');
            trigger.focus();
        }
    });

    // Make options focusable
    list.querySelectorAll('.ob-custom-select-option').forEach(opt => {
        opt.setAttribute('tabindex', '0');
    });

    // Close on click-outside
    document.addEventListener('click', (e) => {
        if (!dropdown.contains(e.target)) {
            dropdown.classList.remove('open');
            trigger.setAttribute('aria-expanded', 'false');
        }
    });
}

function _selectObProvider(value, label) {
    _obSelectedProvider = value;
    obTouched.provider = true;

    // Update trigger text
    const valueEl = document.querySelector('#ob-provider-trigger .ob-custom-select-value');
    if (valueEl) valueEl.textContent = label;

    // Update selected state in list
    document.querySelectorAll('#ob-provider-list .ob-custom-select-option').forEach(opt => {
        const isSel = opt.dataset.value === value;
        opt.classList.toggle('selected', isSel);
        opt.setAttribute('aria-selected', String(isSel));
    });


    // Update API key label, hint, placeholder
    const meta = _PROVIDER_META[value] || _PROVIDER_META.openai;
    const keyLabel = el('ob-api-key-label');
    if (keyLabel) keyLabel.textContent = obI18n(meta.label_i18n, 'API Key');
    const keyHint = el('ob-api-key-hint');
    if (keyHint) keyHint.textContent = obI18n(meta.hint_i18n, '');
    const keyInput = el('ob-openai-key');
    if (keyInput) keyInput.placeholder = meta.placeholder;

    // Show/hide local notice
    const notice = el('obLocalNotice');
    if (notice) notice.classList.toggle('hidden', !meta.local);

    // Hide/show API key input row for local providers
    const keyRow = el('ob-row-openai');
    if (keyRow) keyRow.classList.toggle('hidden', !!meta.local);

    // Toggle provider-specific guide blocks
    const guideIds = ['ob-guide-openai', 'ob-guide-ollama', 'ob-guide-lmstudio', 'ob-guide-groq', 'ob-guide-openrouter'];
    guideIds.forEach(id => {
        const guide = el(id);
        if (guide) guide.classList.toggle('hidden', id !== 'ob-guide-' + value);
    });

    // Reset models when provider changes
    _obModelsLoaded = false;

    // Re-evaluate Next button state (local providers don't need a key)
    _updateNavButtons();
}
window._selectObProvider = _selectObProvider;

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
        // Step 2: Save provider + API key
        const key = el('ob-openai-key')?.value.trim();
        const baseUrl = _PROVIDER_BASE_URLS[_obSelectedProvider] || '';

        // Save provider settings
        try {
            await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    provider_preset: _obSelectedProvider,
                    llm_base_url: baseUrl,
                }),
            });
        } catch (e) { /* best-effort */ }

        if (key) {
            await _saveCredentials({ OPENAI_API_KEY: key });
            el('ob-openai-key').value = '';
            obTouched.openai_key = true;
            await prefillCredentials();
        }
        obGoPage(2);
    } else if (currentPage === 2) {
        // Step 3: Save Spotify creds
        const id = el('ob-spotify-id')?.value.trim();
        const secret = el('ob-spotify-secret')?.value.trim();
        const payload = {};
        if (id) payload.SPOTIPY_CLIENT_ID = id;
        if (secret) payload.SPOTIPY_CLIENT_SECRET = secret;
        if (Object.keys(payload).length > 0) {
            await _saveCredentials(payload);
            if (id) el('ob-spotify-id').value = '';
            if (secret) el('ob-spotify-secret').value = '';
            obTouched.spotify_cred = true;
            await prefillCredentials();
        }
        obGoPage(3);
    } else if (currentPage === 4) {
        // Step 5: Save model
        const model = _obGetEffectiveModel();
        if (model) {
            try {
                await fetch('/api/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model }),
                });
                obTouched.model = true;
                _obAiReady = true;
            } catch (e) { /* best-effort */ }
        }
        obGoPage(5);
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
    const setRow = el('ob-set-' + field);
    const inputWrap = el('ob-input-wrap-' + field);
    if (setRow) setRow.classList.add('hidden');
    if (inputWrap) inputWrap.classList.remove('hidden');
    _obEditingFields.add(field);
    const inputMap = {
        'openai': 'ob-openai-key',
        'spotify-id': 'ob-spotify-id',
        'spotify-secret': 'ob-spotify-secret',
    };
    const inputEl = el(inputMap[field]);
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
    const statusEl = el('ob-spotify-status');
    if (statusEl) statusEl.textContent = obI18n('ob.opening_spotify', 'Opening Spotify…');

    // pywebview desktop: open OAuth in a managed child window
    if (window.pywebview?.api?.open_spotify_auth) {
        window.pywebview.api.open_spotify_auth();
        // Poll for completion since pywebview manages the window
        const poll = setInterval(async () => {
            try {
                const resp = await fetch('/api/spotify/status');
                const data = await resp.json();
                if (data.status === 'authenticated') {
                    clearInterval(poll);
                    _setObSpotifyState(true);
                }
            } catch (e) { /* ignore */ }
        }, 2000);
        setTimeout(() => clearInterval(poll), 120000); // stop after 2 min
        return;
    }

    // Android WebView: navigate in-window (no popup)
    if (/; wv\)/.test(navigator.userAgent)) {
        window.location.href = '/api/spotify/auth';
        return;
    }

    // Browser: open popup
    window.open('/api/spotify/auth', 'spotifyAuth', 'width=480,height=640');
    window.addEventListener('message', async (e) => {
        if (e.data === 'spotify-auth-complete') {
            _setObSpotifyState(true);
        }
    }, { once: true });
}

async function disconnectObSpotify() {
    try {
        await fetch('/api/spotify/disconnect', { method: 'POST' });
        _setObSpotifyState(false);
    } catch (e) {
        const statusEl = el('ob-spotify-status');
        if (statusEl) {
            statusEl.textContent = obI18n('ob.network_error', '❌ Network error.');
            statusEl.className = 'ob-explain ob-error';
        }
    }
}

function _setObSpotifyState(connected) {
    _obSpotifyConnected = connected;
    const btn = el('ob-spotify-btn');
    const statusEl = el('ob-spotify-status');
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
    // Refresh seed card states (Spotify + AI readiness)
    _updateSeedCardStates();
}

/**
 * Update the playlist seed card's enabled/disabled state based on
 * both Spotify connection AND AI readiness (key + model).
 */
function _updateSeedCardStates() {
    const seedCard = el('obSeedPlaylistCard');
    if (!seedCard) return;
    const seedAction = seedCard.querySelector('.ob-seed-action');
    const spotifyHint = el('obSeedConnectHint');
    const aiHint = el('obSeedAiHint');

    const canSeed = _obSpotifyConnected && _obAiReady;

    if (canSeed) {
        seedCard.classList.remove('ob-seed-card--disabled');
        seedCard.style.opacity = '';
        if (seedAction) seedAction.classList.remove('hidden');
        if (spotifyHint) spotifyHint.classList.add('hidden');
        if (aiHint) aiHint.classList.add('hidden');
    } else {
        seedCard.classList.add('ob-seed-card--disabled');
        seedCard.style.opacity = '0.55';
        if (seedAction) seedAction.classList.add('hidden');
        // Show the most relevant hint
        if (!_obAiReady && !_obSpotifyConnected) {
            // Both missing — show AI hint (more actionable since it comes first in flow)
            if (aiHint) { aiHint.classList.remove('hidden'); aiHint.textContent = obI18n('seed.ai_and_spotify_required', 'Set up AI provider and connect Spotify first'); }
            if (spotifyHint) spotifyHint.classList.add('hidden');
        } else if (!_obAiReady) {
            if (aiHint) aiHint.classList.remove('hidden');
            if (spotifyHint) spotifyHint.classList.add('hidden');
        } else {
            // Only Spotify missing
            if (spotifyHint) spotifyHint.classList.remove('hidden');
            if (aiHint) aiHint.classList.add('hidden');
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
    const input = el('ob-import-input');
    if (!input) return;
    input.value = '';
    input.onchange = async () => {
        const file = input.files[0];
        if (!file) return;
        const statusEl = el('ob-import-status');
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
    const body = el(bodyId);
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
    const select = el('ob-model-select');
    if (!select) return;

    const spinner = el('obModelSpinner');
    const errorEl = el('obModelError');
    const freetextWrap = el('obModelFreetext');
    const badge = el('obProviderBadge');

    // Update provider badge
    if (badge) {
        const providerLabel = document.querySelector(`#ob-provider-list .ob-custom-select-option[data-value="${_obSelectedProvider}"]`);
        const providerName = providerLabel ? providerLabel.textContent.trim() : _obSelectedProvider;
        badge.textContent = obI18n('ob.step6_provider_note', 'You chose: {provider}').replace('{provider}', providerName);
    }

    // Show spinner, hide error
    if (spinner) spinner.classList.remove('hidden');
    if (errorEl) errorEl.classList.add('hidden');
    if (freetextWrap) freetextWrap.classList.add('hidden');

    try {
        // Try fetching models from the provider
        const baseUrl = _PROVIDER_BASE_URLS[_obSelectedProvider] || 'https://api.openai.com/v1';

        // First try the /api/llm/fetch_models endpoint (server uses stored API key)
        let models = [];
        let fetchOk = false;
        let currentModel = '';
        try {
            const resp = await fetch('/api/llm/fetch_models', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ base_url: baseUrl }),
            });
            if (resp.ok) {
                const data = await resp.json();
                if (data.models && data.models.length > 0) {
                    models = data.models;
                    fetchOk = true;
                }
            }
        } catch (e) { /* fall through to /api/settings */ }

        // Fallback: get models from /api/settings (also gets current model)
        if (!fetchOk) {
            try {
                const resp = await fetch('/api/settings');
                if (resp.ok) {
                    const data = await resp.json();
                    models = data.available_models || [];
                    currentModel = data.model || '';
                    if (models.length > 0) fetchOk = true;
                }
            } catch (e) { /* ignore */ }
        }

        // If live fetch succeeded, still need the current model for preselection
        if (fetchOk && !currentModel) {
            try {
                const resp = await fetch('/api/settings');
                const data = await resp.json();
                currentModel = data.model || '';
            } catch (e) { /* ignore */ }
        }

        if (fetchOk && models.length > 0) {
            select.innerHTML = '';
            models.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m;
                opt.textContent = m;
                if (m === currentModel) opt.selected = true;
                select.appendChild(opt);
            });
            _obModelsLoaded = true;
        } else {
            // Show error + free-text fallback
            if (errorEl) {
                errorEl.classList.remove('hidden');
                // Show provider-specific error message
                const errText = errorEl.querySelector('.ob-model-error-text');
                if (errText) {
                    const meta = _PROVIDER_META[_obSelectedProvider] || {};
                    if (meta.local) {
                        const providerLabel = document.querySelector(`#ob-provider-list .ob-custom-select-option[data-value="${_obSelectedProvider}"]`);
                        const name = providerLabel ? providerLabel.textContent.trim() : _obSelectedProvider;
                        errText.textContent = obI18n('ob.model_error_local', 'Make sure {provider} is running on your machine.').replace('{provider}', name);
                    } else {
                        errText.textContent = obI18n('ob.model_error_remote', 'Couldn\'t reach that endpoint. Check the base URL and try again.');
                    }
                }
            }
            if (freetextWrap) freetextWrap.classList.remove('hidden');
            // Pre-fill freetext with current model if available
            const ftInput = el('ob-model-freetext');
            if (ftInput && currentModel && !ftInput.value.trim()) {
                ftInput.value = currentModel;
            }
            // Keep the dropdown with a placeholder
            select.innerHTML = '<option value="">—</option>';
        }
        // Refresh cost estimate now that model is known
        _obInitCostWidget();
    } catch (e) {
        if (errorEl) errorEl.classList.remove('hidden');
        if (freetextWrap) freetextWrap.classList.remove('hidden');
    } finally {
        if (spinner) spinner.classList.add('hidden');
    }
}

function obRetryLoadModels() {
    _obModelsLoaded = false;
    obLoadModels();
}
window.obRetryLoadModels = obRetryLoadModels;

/* ── Summary builder (Step 7) ─────────────────────────────────── */

async function obBuildSummary() {
    const rows = [
        { id: 'sum-openai', label: 'ob.sum_openai', fallback: 'OpenAI key', touchKey: 'openai_key' },
        { id: 'sum-spotify-cred', label: 'ob.sum_spotify_cred', fallback: 'Spotify developer app', touchKey: 'spotify_cred' },
        { id: 'sum-spotify-conn', label: 'ob.sum_spotify_conn', fallback: 'Spotify account', touchKey: 'spotify_conn' },
        { id: 'sum-profile', label: 'ob.sum_profile', fallback: 'Taste profile', touchKey: 'profile' },
        { id: 'sum-model', label: 'ob.sum_model', fallback: 'Model', touchKey: 'model' },
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
        if (data.display_name) {
            _obSpotifyDisplayName = data.display_name;
        }
    } catch (e) {}

    // Update spotify_conn touched flag if connected
    if (spotifyStatus && _obSpotifyConnected) {
        obTouched.spotify_conn = true;
    }

    let profileTrained = false;
    try {
        const resp = await fetch('/api/profile/status');
        const data = await resp.json();
        profileTrained = data.trained === true;
    } catch (e) {}

    if (_obProfileImported) obTouched.profile = true;

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
        'sum-profile': 5,
        'sum-model': 4,
    };

    const isReplay = new URLSearchParams(location.search).get('replay') === '1';
    let hasSkipped = false;

    rows.forEach(row => {
        const rowEl = el(row.id);
        if (!rowEl) return;

        const isSet = checks[row.id];
        const touched = obTouched[row.touchKey];

        const statusEl = rowEl.querySelector('.ob-summary-status');
        const labelEl = rowEl.querySelector('.ob-summary-label');
        const subEl = rowEl.querySelector('.ob-summary-sub');
        const editBtn = rowEl.querySelector('.ob-summary-edit');

        // Determine display state
        let state; // 'done', 'previous', 'skipped'
        if (isSet && touched) {
            state = 'done';
        } else if (isSet && !touched) {
            state = 'previous'; // set from previous session
        } else {
            state = 'skipped';
            hasSkipped = true;
        }

        if (statusEl) {
            statusEl.className = 'ob-summary-status ' + (state === 'skipped' ? 'ob-summary-status--skipped' : 'ob-summary-status--done');
            statusEl.textContent = state === 'skipped' ? '⚠' : '✓';
        }

        if (labelEl) {
            labelEl.textContent = obI18n(row.label, row.fallback);
        }

        if (subEl) {
            if (state === 'done') {
                if (row.id === 'sum-spotify-conn' && _obSpotifyDisplayName) {
                    subEl.textContent = obI18n('ob.sum_connected_as', 'Connected as {user}').replace('{user}', _obSpotifyDisplayName);
                } else {
                    subEl.textContent = obI18n('ob.sum_set', 'Set');
                }
            } else if (state === 'previous') {
                subEl.textContent = obI18n('ob.sum_from_previous', '(from previous setup)');
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
    const warning = el('ob-skipped-warning');
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
            const setRow = el('ob-set-' + ids.field);
            const inputWrap = el('ob-input-wrap-' + ids.field);
            const inputEl = el(ids.input);
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

/* ── Step 5 — Provider & Cost Widget ──────────────────────────── */

function _obGetEffectiveModel() {
    const freetext = el('ob-model-freetext');
    const freetextWrap = el('obModelFreetext');
    // Prefer freetext if visible and non-empty
    if (freetext && freetextWrap && !freetextWrap.classList.contains('hidden') && freetext.value.trim()) {
        return freetext.value.trim();
    }
    const select = el('ob-model-select');
    const val = select ? select.value : '';
    // Ignore placeholder values
    if (!val || val === '—' || val === 'Loading…') return 'gpt-4o-mini';
    return val;
}

function _obInitCostWidget() {
    const model = _obGetEffectiveModel();
    if (typeof window._obEstimateCost === 'function') {
        window._obEstimateCost(model, 25);
    }
    // Re-estimate on model select change
    const modelSelect = el('ob-model-select');
    if (modelSelect && !modelSelect._obCostWired) {
        modelSelect.addEventListener('change', () => {
            if (typeof window._obEstimateCost === 'function') {
                window._obEstimateCost(_obGetEffectiveModel(), 25);
            }
        });
        modelSelect._obCostWired = true;
    }
    // Re-estimate on freetext input change
    const freetext = el('ob-model-freetext');
    if (freetext && !freetext._obCostWired) {
        freetext.addEventListener('input', () => {
            if (typeof window._obEstimateCost === 'function') {
                window._obEstimateCost(_obGetEffectiveModel(), 25);
            }
        });
        freetext._obCostWired = true;
    }
}
window._obInitCostWidget = _obInitCostWidget;

/* onObProviderChange — no longer needed; provider is handled by custom dropdown in Step 2 */

/* ── Init ─────────────────────────────────────────────────────── */

(async function () {
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
    await _checkObAiReadiness();
    _updateIndicators();
})();

/** Check if AI provider key + model are already configured. */
async function _checkObAiReadiness() {
    try {
        const [credResp, settingsResp] = await Promise.all([
            fetch('/api/settings/credentials'),
            fetch('/api/settings'),
        ]);
        const creds = await credResp.json();
        const settings = await settingsResp.json();

        const isLocal = (_PROVIDER_META[_obSelectedProvider] || {}).local === true;
        const hasKey = creds.OPENAI_API_KEY?.is_set === true || isLocal;
        const hasModel = !!(settings.model);

        _obAiReady = hasKey && hasModel;
    } catch (e) {
        _obAiReady = false;
    }
}

