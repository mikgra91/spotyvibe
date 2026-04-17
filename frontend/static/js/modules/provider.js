/**
 * provider.js — Custom LLM endpoint management (Wave 4 E.1)
 */
import { i18n } from './i18n.js';
import { showToast } from './ui.js';
import { el } from './dom.js';

export const PROVIDER_PRESETS = {
    openai:     { id: 'openai',     name_i18n: 'provider.openai',     default_base_url: 'https://api.openai.com/v1',       local: false, doc_url: 'https://platform.openai.com/api-keys' },
    ollama:     { id: 'ollama',     name_i18n: 'provider.ollama',     default_base_url: 'http://localhost:11434/v1',        local: true,  doc_url: 'https://ollama.com/download' },
    lmstudio:   { id: 'lmstudio',   name_i18n: 'provider.lmstudio',   default_base_url: 'http://localhost:1234/v1',         local: true,  doc_url: 'https://lmstudio.ai/' },
    groq:       { id: 'groq',       name_i18n: 'provider.groq',       default_base_url: 'https://api.groq.com/openai/v1',  local: false, doc_url: 'https://console.groq.com/keys' },
    openrouter: { id: 'openrouter', name_i18n: 'provider.openrouter', default_base_url: 'https://openrouter.ai/api/v1',    local: false, doc_url: 'https://openrouter.ai/keys' },
};

let _currentPreset = 'openai';

export function onProviderChange() {
    const select = el('settings-provider');
    if (!select) return;
    const preset = select.value;
    _currentPreset = preset;
    const p = PROVIDER_PRESETS[preset] || PROVIDER_PRESETS.openai;

    // Base URL row — always hidden (presets have fixed URLs)
    const urlRow = el('providerBaseUrlRow');
    if (urlRow) urlRow.classList.add('hidden');

    // Set default base URL
    const urlInput = el('settings-base-url');
    if (urlInput) urlInput.value = p.default_base_url;

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
}

export async function fetchProviderModels() {
    const select = el('settings-provider');
    const preset = select ? select.value : 'openai';
    const p = PROVIDER_PRESETS[preset] || PROVIDER_PRESETS.openai;

    const base_url = p.default_base_url;

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
    }).catch(() => {});
}

