/**
 * provider.js — Custom LLM endpoint management (Wave 4 E.1)
 */
import { i18n } from './i18n.js';
import { showToast } from './ui.js';

export const PROVIDER_PRESETS = {
    openai:     { id: 'openai',     name_i18n: 'provider.openai',     default_base_url: 'https://api.openai.com/v1',       local: false, doc_url: 'https://platform.openai.com/api-keys' },
    ollama:     { id: 'ollama',     name_i18n: 'provider.ollama',     default_base_url: 'http://localhost:11434/v1',        local: true,  doc_url: 'https://ollama.com/download' },
    lmstudio:   { id: 'lmstudio',   name_i18n: 'provider.lmstudio',   default_base_url: 'http://localhost:1234/v1',         local: true,  doc_url: 'https://lmstudio.ai/' },
    groq:       { id: 'groq',       name_i18n: 'provider.groq',       default_base_url: 'https://api.groq.com/openai/v1',  local: false, doc_url: 'https://console.groq.com/keys' },
    openrouter: { id: 'openrouter', name_i18n: 'provider.openrouter', default_base_url: 'https://openrouter.ai/api/v1',    local: false, doc_url: 'https://openrouter.ai/keys' },
    custom:     { id: 'custom',     name_i18n: 'provider.custom',     default_base_url: '',                                local: false, doc_url: null },
};

let _currentPreset = 'openai';

export function onProviderChange() {
    const select = document.getElementById('settings-provider');
    if (!select) return;
    const preset = select.value;
    _currentPreset = preset;
    const p = PROVIDER_PRESETS[preset] || PROVIDER_PRESETS.openai;

    // Base URL row visibility
    const urlRow = document.getElementById('providerBaseUrlRow');
    if (urlRow) urlRow.classList.toggle('hidden', preset !== 'custom');

    // Set default base URL
    const urlInput = document.getElementById('settings-base-url');
    if (urlInput && preset !== 'custom') urlInput.value = p.default_base_url;

    // API key label
    const keyLabel = document.getElementById('settings-api-key-label');
    if (keyLabel) keyLabel.textContent = i18n(`provider.api_key_label_${preset}`, 'API Key');

    // API key hint
    const keyHint = document.getElementById('settings-api-key-hint');
    if (keyHint) keyHint.textContent = i18n(`provider.api_key_hint_${preset}`, '');

    // Local notice
    const notice = document.getElementById('providerLocalNotice');
    if (notice) notice.classList.toggle('hidden', !p.local);

    // Clear fetch error
    const fetchErr = document.getElementById('providerFetchError');
    if (fetchErr) { fetchErr.textContent = ''; fetchErr.classList.add('hidden'); }
}

export async function fetchProviderModels() {
    const select = document.getElementById('settings-provider');
    const preset = select ? select.value : 'openai';
    const p = PROVIDER_PRESETS[preset] || PROVIDER_PRESETS.openai;

    const urlInput = document.getElementById('settings-base-url');
    const base_url = (preset === 'custom' && urlInput) ? urlInput.value.trim() : p.default_base_url;

    const keyInput = document.getElementById('settings-api-key');
    const api_key = keyInput ? keyInput.value.trim() : '';

    const btn = document.getElementById('btnFetchModels');
    if (btn) btn.disabled = true;

    const fetchErr = document.getElementById('providerFetchError');
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

        const modelSelect = document.getElementById('settings-model');
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
    const select = document.getElementById('settings-model');
    const freetext = document.getElementById('settings-model-freetext');
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
    if (_currentPreset === 'custom') {
        const urlInput = document.getElementById('settings-base-url');
        return urlInput ? urlInput.value.trim() : '';
    }
    return p.default_base_url;
}

export function init() {
    window.onProviderChange = onProviderChange;
    window.fetchProviderModels = fetchProviderModels;
    window.toggleModelFreeText = toggleModelFreeText;

    // On page load, read current provider from settings and set UI
    fetch('/api/settings').then(r => r.json()).then(data => {
        _currentPreset = data.provider_preset || 'openai';
        const select = document.getElementById('settings-provider');
        if (select) select.value = _currentPreset;
        const urlInput = document.getElementById('settings-base-url');
        if (urlInput && data.llm_base_url) urlInput.value = data.llm_base_url;
    }).catch(() => {});
}

