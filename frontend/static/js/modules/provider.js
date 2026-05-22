/**
 * provider.js — Custom LLM endpoint management (Wave 4 E.1)
 */
import { i18n } from './i18n.js';
import { showToast } from './ui.js';
import { el } from './dom.js';

export const PROVIDER_PRESETS = {
    openai:     { id: 'openai',     name_i18n: 'provider.openai',     default_base_url: 'https://api.openai.com/v1',       local: false, doc_url: 'https://platform.openai.com/api-keys',
        suggested_models: [
            'gpt-5.4-mini',
            'gpt-5.4',
        ],
    },
    ollama:     { id: 'ollama',     name_i18n: 'provider.ollama',     default_base_url: 'http://localhost:11434/v1',        local: true,  doc_url: 'https://ollama.com/download' },
    lmstudio:   { id: 'lmstudio',   name_i18n: 'provider.lmstudio',   default_base_url: 'http://localhost:1234/v1',         local: true,  doc_url: 'https://lmstudio.ai/' },
    llamacpp:   { id: 'llamacpp',   name_i18n: 'provider.llamacpp',   default_base_url: 'http://localhost:8080/v1',         local: true,  doc_url: 'https://github.com/ggerganov/llama.cpp' },
    openrouter: { id: 'openrouter', name_i18n: 'provider.openrouter', default_base_url: 'https://openrouter.ai/api/v1',    local: false, doc_url: 'https://openrouter.ai/keys',
        // 2026-05-20: ordered by the n=3 cross-model eval (see
        // evaluation/model-performance-result.md). gpt-5.4-mini is the
        // default — best quality (80.6% must-have cite rate). Gemini 3.1
        // Flash Lite is the cheap/fast alternative (~3x cheaper, ~2.4x
        // faster, but 58.9% cite rate). DeepSeek V4 Flash was removed
        // (60-80% hidden reasoning-token overhead). Users can still add
        // any model via free-text or the fetch button.
        suggested_models: [
            'openai/gpt-5.4-mini',
            'google/gemini-3.1-flash-lite',
        ],
    },
};

let _currentPreset = 'openai';

export function onProviderChange(opts) {
    const select = el('settings-provider');
    if (!select) return;
    const preset = select.value;
    _currentPreset = preset;
    const p = PROVIDER_PRESETS[preset] || PROVIDER_PRESETS.openai;
    // `resetUrl` defaults to true (user-driven onchange clobbers stale URL).
    // The initial sync from saved settings passes `{ resetUrl: false }` so a
    // user-customised port (e.g. llama.cpp on :9000) survives a page reload.
    const resetUrl = !opts || opts.resetUrl !== false;

    // Local providers expose the Base URL field so users can point at
    // non-default ports (llama.cpp 8080, custom Ollama setups, etc.).
    // Remote presets keep it hidden — their URLs are fixed.
    const urlRow = el('providerBaseUrlRow');
    if (urlRow) urlRow.classList.toggle('hidden', !p.local);

    const urlInput = el('settings-base-url');
    if (urlInput && resetUrl) urlInput.value = p.default_base_url;

    // API key label
    const keyLabel = el('settings-api-key-label');
    if (keyLabel) keyLabel.textContent = i18n(`provider.api_key_label_${preset}`, 'API Key');

    // API key hint
    const keyHint = el('settings-api-key-hint');
    if (keyHint) keyHint.textContent = i18n(`provider.api_key_hint_${preset}`, '');

    // Update credentials modal label dynamically (Wave 4 E.1)
    const credLabel = el('label-OPENAI_API_KEY');
    if (credLabel) {
        const providerName = i18n(p.name_i18n, preset);
        credLabel.textContent = p.local
            ? i18n('provider.api_key_not_needed', 'API Key (not needed)')
            : i18n('provider.cred_label_tpl', '{provider} API Key').replace('{provider}', providerName);
    }

    // Local notice
    const notice = el('providerLocalNotice');
    if (notice) notice.classList.toggle('hidden', !p.local);

    // Clear fetch error
    const fetchErr = el('providerFetchError');
    if (fetchErr) { fetchErr.textContent = ''; fetchErr.classList.add('hidden'); }

    // Pre-populate model dropdown with provider's suggested models. User can
    // still override via free-text or fetch button. Skip on initial load
    // (resetUrl=false) so saved settings aren't clobbered.
    if (resetUrl && p.suggested_models && p.suggested_models.length) {
        const modelSelect = el('settings-model');
        if (modelSelect) {
            const currentVal = modelSelect.value;
            modelSelect.innerHTML = '';
            p.suggested_models.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m;
                opt.textContent = m;
                modelSelect.appendChild(opt);
            });
            if (p.suggested_models.includes(currentVal)) modelSelect.value = currentVal;
        }
    }
}

export async function fetchProviderModels() {
    const select = el('settings-provider');
    const preset = select ? select.value : 'openai';
    const p = PROVIDER_PRESETS[preset] || PROVIDER_PRESETS.openai;

    // Prefer the user-entered Base URL when the field is visible (local
    // providers). Falls back to the preset default for remote providers.
    const urlInput = el('settings-base-url');
    const base_url = (urlInput && urlInput.value && urlInput.value.trim()) || p.default_base_url;

    const keyInput = el('settings-api-key');
    const api_key = keyInput ? keyInput.value.trim() : '';

    const btn = el('btnFetchModels');
    if (btn) btn.disabled = true;

    const fetchErr = el('providerFetchError');
    if (fetchErr) { fetchErr.textContent = ''; fetchErr.classList.add('hidden'); }

    try {
        const resp = await fetch('/api/llm/fetch_models', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ base_url, api_key }),
        });
        const data = await resp.json();

        if (!resp.ok || data.error) {
            if (fetchErr) {
                fetchErr.textContent = i18n('provider.fetch_failed', "Couldn't reach that endpoint.");
                fetchErr.classList.remove('hidden');
            }
            return;
        }

        const modelSelect = el('settings-model');
        if (modelSelect && data.models) {
            const currentVal = modelSelect.value;
            modelSelect.innerHTML = '';
            data.models.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m;
                opt.textContent = m;
                modelSelect.appendChild(opt);
            });
            // Restore previous selection if still in the list
            if (data.models.includes(currentVal)) modelSelect.value = currentVal;
            showToast(i18n('provider.fetch_success', 'Loaded {count} models.').replace('{count}', data.models.length));
        }
    } catch (e) {
        if (fetchErr) {
            fetchErr.textContent = i18n('provider.fetch_failed', "Couldn't reach that endpoint.");
            fetchErr.classList.remove('hidden');
        }
    } finally {
        if (btn) btn.disabled = false;
    }
}

export function toggleModelFreeText() {
    const select = el('settings-model');
    const freetext = el('settings-model-freetext');
    if (!select || !freetext) return;
    const showFreetext = select.classList.contains('hidden');
    if (showFreetext) {
        // Switch back to dropdown
        select.classList.remove('hidden');
        freetext.classList.add('hidden');
        select.value = freetext.value || select.options[0]?.value || '';
    } else {
        // Switch to free-text
        freetext.value = select.value;
        select.classList.add('hidden');
        freetext.classList.remove('hidden');
        freetext.focus();
    }
}

export function getCurrentPreset() { return _currentPreset; }
export function getBaseUrl() {
    const p = PROVIDER_PRESETS[_currentPreset] || PROVIDER_PRESETS.openai;
    return p.default_base_url;
}

export function init() {
    window.onProviderChange = onProviderChange;
    window.fetchProviderModels = fetchProviderModels;
    window.toggleModelFreeText = toggleModelFreeText;

    // On page load, read current provider from settings and set UI
    fetch('/api/settings').then(r => r.json()).then(data => {
        _currentPreset = data.provider_preset || 'openai';
        const select = el('settings-provider');
        if (select) select.value = _currentPreset;
        const urlInput = el('settings-base-url');
        if (urlInput && data.llm_base_url) urlInput.value = data.llm_base_url;
        // Apply provider-dependent visibility (Base URL row) WITHOUT
        // clobbering the saved URL we just restored.
        onProviderChange({ resetUrl: false });
    }).catch(() => {});
}

