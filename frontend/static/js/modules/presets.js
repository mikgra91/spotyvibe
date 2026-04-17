/**
 * presets.js — Generation preset CRUD, built-in catalogue, import/export,
 * dropdown rendering.
 *
 * Presets are entirely client-side (localStorage). Built-in presets are
 * immutable; user presets support rename, delete, clone, reorder, import/export.
 */

import { i18n } from './i18n.js';
import { showToast } from './ui.js';
import { el } from './dom.js';

// ── Empty audio filters template ────────────────────────────────────

const EMPTY_FILTERS = {
    energy:       { min: null, max: null },
    valence:      { min: null, max: null },
    tempo:        { min: null, max: null },
    danceability: { min: null, max: null },
    acousticness: { min: null, max: null },
};

// ── Built-in presets ────────────────────────────────────────────────

export const BUILTIN_PRESETS = [
    {
        id: 'builtin_safe_picks',
        name: 'Safe picks',
        builtin: true,
        version: 1,
        settings: {
            size: 20,
            exploration_notch: 1,
            new_artist_pct: 10,
            emerging_only: false,
            temperature: 0.5,
            audio_filters: { ...EMPTY_FILTERS },
            model_override: null,
        },
    },
    {
        id: 'builtin_balanced',
        name: 'Balanced',
        builtin: true,
        version: 1,
        settings: {
            size: 30,
            exploration_notch: 3,
            new_artist_pct: 30,
            emerging_only: false,
            temperature: 0.8,
            audio_filters: { ...EMPTY_FILTERS },
            model_override: null,
        },
    },
    {
        id: 'builtin_deep_discovery',
        name: 'Deep discovery',
        builtin: true,
        version: 1,
        settings: {
            size: 30,
            exploration_notch: 5,
            new_artist_pct: 90,
            emerging_only: true,
            temperature: 1.0,
            audio_filters: { ...EMPTY_FILTERS },
            model_override: null,
        },
    },
];

// ── State ───────────────────────────────────────────────────────────

let _userPresets = [];
let _activePresetId = null;
let _dropdownOpen = false;
let _itemMenuOpen = null; // id of preset whose ⋯ menu is open

const STORAGE_KEY = 'sv.presets.user';
const ACTIVE_KEY  = 'sv.presets.active';

// ── Persistence ─────────────────────────────────────────────────────

function _loadUserPresets() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        _userPresets = raw ? JSON.parse(raw) : [];
    } catch (_) { _userPresets = []; }
}

function _saveUserPresets() {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(_userPresets));
    } catch (_) { /* ignore */ }
}

function _loadActiveId() {
    try {
        _activePresetId = localStorage.getItem(ACTIVE_KEY) || 'builtin_balanced';
    } catch (_) { _activePresetId = 'builtin_balanced'; }
}

function _saveActiveId() {
    try {
        localStorage.setItem(ACTIVE_KEY, _activePresetId || '');
    } catch (_) { /* ignore */ }
}

// ── Getters ─────────────────────────────────────────────────────────

export function getAllPresets() {
    return [..._userPresets, ...BUILTIN_PRESETS];
}

export function getActivePreset() {
    if (!_activePresetId) return null;
    return getAllPresets().find(p => p.id === _activePresetId) || null;
}

export function getUserPresets() { return _userPresets; }

// ── Apply preset to form ────────────────────────────────────────────

function _applyPresetToForm(preset) {
    if (!preset || !preset.settings) return;
    const s = preset.settings;

    // Size slider
    const sizeSliders = document.querySelectorAll('.gen-size-slider');
    sizeSliders.forEach(sl => {
        sl.value = s.size || 20;
        sl.dispatchEvent(new Event('input'));
    });

    // Exploration — import dynamically to avoid circular deps
    import('./exploration.js').then(Exploration => {
        if (s.exploration_notch && s.exploration_notch !== 'custom') {
            Exploration.setNotch(s.exploration_notch);
        }
    });

    // New artist %
    const napField = el('settings-new-artist-pct');
    if (napField && s.new_artist_pct != null) napField.value = s.new_artist_pct;
    const advNap = el('genNewArtistPct');
    if (advNap && s.new_artist_pct != null) advNap.value = s.new_artist_pct;

    // Emerging only
    const emergingCb = el('emergingArtistsCheckbox');
    if (emergingCb && s.emerging_only != null) emergingCb.checked = s.emerging_only;

    // Audio filters
    if (s.audio_filters) {
        for (const [key, range] of Object.entries(s.audio_filters)) {
            const minEl = el(`af-${key}-min`);
            const maxEl = el(`af-${key}-max`);
            if (minEl) minEl.value = range.min != null ? range.min : '';
            if (maxEl) maxEl.value = range.max != null ? range.max : '';
        }
        // Update filter hints
        if (typeof window.updateAllFilterHints === 'function') window.updateAllFilterHints();
    }
}

// ── Collect current form state into a settings object ───────────────

function _collectCurrentSettings() {
    const sizeSlider = document.querySelector('.gen-size-slider');
    const size = sizeSlider ? parseInt(sizeSlider.value, 10) : 20;

    let explorationNotch = 3;
    let temperature = 0.8;
    try {
        const Exploration = window._explorationModule;
        if (Exploration) {
            explorationNotch = Exploration.getCurrentNotch();
            temperature = Exploration.getTemperature();
        }
    } catch (_) { /* ignore */ }

    const napField = el('genNewArtistPct') || el('settings-new-artist-pct');
    const new_artist_pct = napField ? parseInt(napField.value, 10) || 30 : 30;

    const emergingCb = el('emergingArtistsCheckbox');
    const emerging_only = emergingCb ? emergingCb.checked : false;

    const audio_filters = {};
    for (const key of ['energy', 'valence', 'tempo', 'danceability', 'acousticness']) {
        const minEl = el(`af-${key}-min`);
        const maxEl = el(`af-${key}-max`);
        audio_filters[key] = {
            min: minEl && minEl.value !== '' ? parseFloat(minEl.value) : null,
            max: maxEl && maxEl.value !== '' ? parseFloat(maxEl.value) : null,
        };
    }

    return {
        size,
        exploration_notch: explorationNotch,
        new_artist_pct,
        emerging_only,
        temperature,
        audio_filters,
        model_override: null,
    };
}

// ── Dropdown rendering ──────────────────────────────────────────────

function _renderDropdown() {
    const list = el('presetDropdownList');
    if (!list) return;
    list.innerHTML = '';

    const hasUserPresets = _userPresets.length > 0;

    // User presets section
    if (hasUserPresets) {
        const header = document.createElement('li');
        header.className = 'preset-section-header';
        header.setAttribute('data-i18n', 'preset.your_presets');
        header.textContent = i18n('preset.your_presets', 'Your presets');
        list.appendChild(header);

        for (const preset of _userPresets) {
            list.appendChild(_createPresetItem(preset, false));
        }

        const divider = document.createElement('li');
        divider.className = 'preset-divider';
        list.appendChild(divider);
    }

    // Built-in section
    const builtinHeader = document.createElement('li');
    builtinHeader.className = 'preset-section-header';
    builtinHeader.setAttribute('data-i18n', 'preset.builtin_header');
    builtinHeader.textContent = i18n('preset.builtin_header', 'Built-in');
    list.appendChild(builtinHeader);

    for (const preset of BUILTIN_PRESETS) {
        list.appendChild(_createPresetItem(preset, true));
    }

    // Footer actions
    const footer = document.createElement('li');
    footer.className = 'preset-dropdown-footer';
    footer.innerHTML = `
        <button onclick="window._presetSaveAs()">${i18n('preset.save_current', '💾 Save current as preset…')}</button>
        <button onclick="window._presetOpenManager()">${i18n('nav.manage_presets', '⚙ Manage presets…')}</button>
    `;
    list.appendChild(footer);
}

function _createPresetItem(preset, isBuiltin) {
    const li = document.createElement('li');
    li.className = 'preset-item' + (_activePresetId === preset.id ? ' preset-item--active' : '');
    li.setAttribute('role', 'option');
    li.setAttribute('data-preset-id', preset.id);

    const nameKey = isBuiltin ? `preset.${preset.id.replace('builtin_', 'builtin_')}` : null;
    const displayName = isBuiltin
        ? i18n(`preset.${preset.id}`, preset.name)
        : preset.name;

    let actionHtml = '';
    if (isBuiltin) {
        actionHtml = `<button class="preset-item-action" onclick="event.stopPropagation(); window._presetClone('${preset.id}')" title="${i18n('preset.clone', 'Clone')}">📋</button>`;
    } else {
        actionHtml = `<button class="preset-item-action" onclick="event.stopPropagation(); window._presetItemMenu('${preset.id}', this)" title="More">⋯</button>`;
    }

    li.innerHTML = `
        <span class="preset-item-name">${_escHtml(displayName)}</span>
        ${_activePresetId === preset.id ? '<span class="preset-item-check">✓</span>' : ''}
        ${actionHtml}
    `;

    li.addEventListener('click', () => _selectPreset(preset.id));
    return li;
}

function _escHtml(s) {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
}

// ── Select preset ───────────────────────────────────────────────────

function _selectPreset(id) {
    _activePresetId = id;
    _saveActiveId();
    const preset = getAllPresets().find(p => p.id === id);
    if (preset) _applyPresetToForm(preset);
    _updateTriggerLabel();
    _closeDropdown();
    _renderDropdown();
    _updateActiveIndicator();
}

// ── Trigger label ───────────────────────────────────────────────────

function _updateTriggerLabel() {
    const nameEl = el('presetDropdownName');
    if (!nameEl) return;
    const preset = getActivePreset();
    if (!preset) {
        nameEl.textContent = i18n('preset.custom_unsaved', 'Custom (unsaved)');
        return;
    }
    const suffix = preset.builtin ? ' ' + i18n('preset.builtin_suffix', '(built-in)') : '';
    const name = preset.builtin ? i18n(`preset.${preset.id}`, preset.name) : preset.name;
    nameEl.textContent = name + suffix;
}

// ── Active indicator above Generate button ──────────────────────────

function _updateActiveIndicator() {
    const indicators = document.querySelectorAll('.preset-active-indicator');
    const preset = getActivePreset();
    const text = preset
        ? i18n('preset.using', 'Using preset: {name}').replace('{name}', preset.builtin ? i18n(`preset.${preset.id}`, preset.name) : preset.name)
        : i18n('preset.custom_unsaved', 'Custom (unsaved)');
    indicators.forEach(el => el.textContent = text);
}

// ── Dropdown open/close ─────────────────────────────────────────────

export function togglePresetDropdown() {
    _dropdownOpen ? _closeDropdown() : _openDropdown();
}

function _openDropdown() {
    _renderDropdown();
    const list = el('presetDropdownList');
    const trigger = el('presetDropdownTrigger');
    if (list) list.classList.remove('hidden');
    if (trigger) trigger.setAttribute('aria-expanded', 'true');
    _dropdownOpen = true;
}

function _closeDropdown() {
    const list = el('presetDropdownList');
    const trigger = el('presetDropdownTrigger');
    if (list) list.classList.add('hidden');
    if (trigger) trigger.setAttribute('aria-expanded', 'false');
    _dropdownOpen = false;
    _itemMenuOpen = null;
}

// ── Clone ───────────────────────────────────────────────────────────

function _clonePreset(id) {
    const src = getAllPresets().find(p => p.id === id);
    if (!src) return;
    const copy = {
        id: 'user_' + Date.now(),
        name: (src.builtin ? i18n(`preset.${src.id}`, src.name) : src.name) + ' ' + i18n('preset.clone_copy_suffix', '(copy)'),
        builtin: false,
        version: 1,
        settings: JSON.parse(JSON.stringify(src.settings)),
    };
    _userPresets.unshift(copy);
    _saveUserPresets();
    _selectPreset(copy.id);
}

// ── Item menu (⋯) ──────────────────────────────────────────────────

function _showItemMenu(presetId, anchor) {
    _closeAllItemMenus();
    const row = anchor.closest('.preset-item');
    if (!row) return;
    row.style.position = 'relative';
    const menu = document.createElement('div');
    menu.className = 'preset-item-menu';
    menu.innerHTML = `
        <button onclick="event.stopPropagation(); window._presetRename('${presetId}')">${i18n('preset.rename', 'Rename')}</button>
        <button onclick="event.stopPropagation(); window._presetExportSingle('${presetId}')">${i18n('preset.export', 'Export')}</button>
        <button onclick="event.stopPropagation(); window._presetDelete('${presetId}')">${i18n('preset.delete', 'Delete')}</button>
    `;
    row.appendChild(menu);
    _itemMenuOpen = presetId;
}

function _closeAllItemMenus() {
    document.querySelectorAll('.preset-item-menu').forEach(el => el.remove());
    _itemMenuOpen = null;
}

// ── Rename ──────────────────────────────────────────────────────────

function _renamePreset(id) {
    _closeAllItemMenus();
    const preset = _userPresets.find(p => p.id === id);
    if (!preset) return;
    const newName = prompt(i18n('preset.name_label', 'Name'), preset.name);
    if (newName && newName.trim()) {
        preset.name = newName.trim().slice(0, 40);
        _saveUserPresets();
        _renderDropdown();
        _updateTriggerLabel();
        _renderManager();
    }
}

// ── Delete ──────────────────────────────────────────────────────────

function _deletePreset(id) {
    _closeAllItemMenus();
    _userPresets = _userPresets.filter(p => p.id !== id);
    _saveUserPresets();
    if (_activePresetId === id) {
        _activePresetId = 'builtin_balanced';
        _saveActiveId();
        _updateTriggerLabel();
        _updateActiveIndicator();
    }
    _renderDropdown();
    _renderManager();
}

// ── Export single ───────────────────────────────────────────────────

function _exportSingle(id) {
    const preset = getAllPresets().find(p => p.id === id);
    if (!preset) return;
    const blob = new Blob([JSON.stringify(preset, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `spotyvibe_preset_${preset.name.replace(/\s+/g, '_').toLowerCase()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// ── Save as (new preset from current form) ──────────────────────────

function _openSaveAsDialog() {
    _closeDropdown();
    const modal = el('savePresetModal');
    if (modal) modal.classList.add('open');
    const input = el('savePresetInput');
    if (input) { input.value = ''; input.focus(); }
}

export function confirmSaveAsPreset() {
    const input = el('savePresetInput');
    const name = (input ? input.value : '').trim();
    if (!name) return;

    const preset = {
        id: 'user_' + Date.now(),
        name: name.slice(0, 40),
        builtin: false,
        version: 1,
        settings: _collectCurrentSettings(),
    };
    _userPresets.unshift(preset);
    _saveUserPresets();
    _activePresetId = preset.id;
    _saveActiveId();
    _updateTriggerLabel();
    _updateActiveIndicator();

    const modal = el('savePresetModal');
    if (modal) modal.classList.remove('open');
    showToast(i18n('preset.using', 'Using preset: {name}').replace('{name}', name));
}

// ── Mark form as "custom (unsaved)" when hand-editing ───────────────

export function markCustomUnsaved() {
    _activePresetId = null;
    _saveActiveId();
    _updateTriggerLabel();
    _updateActiveIndicator();
}

// ── Preset manager modal ────────────────────────────────────────────

function _openManager() {
    _closeDropdown();
    _renderManager();
    const modal = el('presetManagerModal');
    if (modal) modal.classList.add('open');
}

function _renderManager() {
    const userList = el('presetManagerUserList');
    const builtinList = el('presetManagerBuiltinList');
    if (!userList || !builtinList) return;

    // User rows
    userList.innerHTML = '';
    for (const preset of _userPresets) {
        const li = document.createElement('li');
        li.className = 'preset-manager-row';
        li.setAttribute('data-preset-id', preset.id);
        li.innerHTML = `
            <span class="preset-manager-drag" title="Drag to reorder">⠿</span>
            <span class="preset-manager-name">${_escHtml(preset.name)}</span>
            <button class="preset-manager-action" onclick="window._presetExportSingle('${preset.id}')" title="${i18n('preset.export', 'Export')}">⬇</button>
            <button class="preset-manager-action delete" onclick="window._presetDelete('${preset.id}')" title="${i18n('preset.delete', 'Delete')}">✕</button>
        `;
        // Click name to rename
        const nameEl = li.querySelector('.preset-manager-name');
        nameEl.addEventListener('click', () => _inlineRename(preset.id, nameEl));
        userList.appendChild(li);
    }

    // Built-in rows
    builtinList.innerHTML = '';
    for (const preset of BUILTIN_PRESETS) {
        const li = document.createElement('li');
        li.className = 'preset-manager-row';
        li.innerHTML = `
            <span class="preset-manager-name">${_escHtml(i18n('preset.' + preset.id, preset.name))}</span>
            <button class="preset-manager-action" onclick="window._presetClone('${preset.id}')" title="${i18n('preset.clone', 'Clone')}">📋</button>
        `;
        builtinList.appendChild(li);
    }

    // Setup drag-and-drop for user list
    _setupDragReorder(userList);
}

function _inlineRename(id, nameEl) {
    const preset = _userPresets.find(p => p.id === id);
    if (!preset) return;
    const input = document.createElement('input');
    input.className = 'preset-manager-name-input';
    input.value = preset.name;
    input.maxLength = 40;
    nameEl.replaceWith(input);
    input.focus();
    input.select();

    const commit = () => {
        const val = input.value.trim();
        if (val) preset.name = val;
        _saveUserPresets();
        _renderManager();
        _updateTriggerLabel();
    };
    input.addEventListener('blur', commit);
    input.addEventListener('keydown', e => {
        if (e.key === 'Enter') { e.preventDefault(); commit(); }
        if (e.key === 'Escape') { _renderManager(); }
    });
}

// ── Drag-and-drop reorder (minimal vanilla implementation) ──────────

function _setupDragReorder(listEl) {
    let dragItem = null;
    let placeholder = null;

    listEl.querySelectorAll('.preset-manager-drag').forEach(handle => {
        handle.addEventListener('pointerdown', e => {
            dragItem = handle.closest('.preset-manager-row');
            if (!dragItem) return;
            e.preventDefault();
            dragItem.style.opacity = '0.5';
            placeholder = document.createElement('li');
            placeholder.className = 'preset-manager-row';
            placeholder.style.height = dragItem.offsetHeight + 'px';
            placeholder.style.border = '1px dashed var(--border)';
            placeholder.style.borderRadius = 'var(--radius-sm)';

            const onMove = (ev) => {
                const target = _getDropTarget(ev, listEl);
                if (target && target !== dragItem) {
                    const rect = target.getBoundingClientRect();
                    const midY = rect.top + rect.height / 2;
                    if (ev.clientY < midY) {
                        listEl.insertBefore(placeholder, target);
                    } else {
                        listEl.insertBefore(placeholder, target.nextSibling);
                    }
                }
            };

            const onUp = () => {
                document.removeEventListener('pointermove', onMove);
                document.removeEventListener('pointerup', onUp);
                if (dragItem) dragItem.style.opacity = '1';
                if (placeholder && placeholder.parentNode) {
                    listEl.insertBefore(dragItem, placeholder);
                    placeholder.remove();
                }
                // Rebuild order from DOM
                const newOrder = [];
                listEl.querySelectorAll('.preset-manager-row[data-preset-id]').forEach(row => {
                    const id = row.getAttribute('data-preset-id');
                    const p = _userPresets.find(up => up.id === id);
                    if (p) newOrder.push(p);
                });
                _userPresets = newOrder;
                _saveUserPresets();
                dragItem = null;
                placeholder = null;
            };

            document.addEventListener('pointermove', onMove);
            document.addEventListener('pointerup', onUp);
        });
    });
}

function _getDropTarget(ev, listEl) {
    const rows = listEl.querySelectorAll('.preset-manager-row[data-preset-id]');
    for (const row of rows) {
        const rect = row.getBoundingClientRect();
        if (ev.clientY >= rect.top && ev.clientY <= rect.bottom) return row;
    }
    return null;
}

// ── Import ──────────────────────────────────────────────────────────

export function importPresetFile() {
    const input = el('presetImportInput');
    if (!input) return;
    input.click();
}

function _handleImportFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (evt) => {
        try {
            const data = JSON.parse(evt.target.result);
            if (!data || !data.settings || !data.name) throw new Error('Invalid');
            const preset = {
                id: 'user_' + Date.now(),
                name: String(data.name).slice(0, 40),
                builtin: false,
                version: data.version || 1,
                settings: data.settings,
            };
            _userPresets.unshift(preset);
            _saveUserPresets();
            _renderDropdown();
            _renderManager();
            showToast(i18n('preset.using', 'Using preset: {name}').replace('{name}', preset.name));
        } catch (_) {
            showToast(i18n('preset.import_failed', 'Import failed.'));
        }
    };
    reader.readAsText(file);
    e.target.value = ''; // reset so same file can be re-imported
}

// ── Close outside click ─────────────────────────────────────────────

function _handleDocClick(e) {
    const wrap = document.querySelector('.preset-dropdown-wrap');
    if (_dropdownOpen && wrap && !wrap.contains(e.target)) {
        _closeDropdown();
    }
    if (_itemMenuOpen && !e.target.closest('.preset-item-menu')) {
        _closeAllItemMenus();
    }
}

// ── Init ────────────────────────────────────────────────────────────

export function init() {
    _loadUserPresets();
    _loadActiveId();
    _updateTriggerLabel();
    _updateActiveIndicator();

    // Wire global functions for onclick handlers in templates
    window.togglePresetDropdown = togglePresetDropdown;
    window.confirmSaveAsPreset = confirmSaveAsPreset;
    window.importPresetFile = importPresetFile;
    window._presetSaveAs = _openSaveAsDialog;
    window._presetOpenManager = _openManager;
    window._presetClone = _clonePreset;
    window._presetItemMenu = _showItemMenu;
    window._presetRename = _renamePreset;
    window._presetDelete = _deletePreset;
    window._presetExportSingle = _exportSingle;

    // Import file input
    const importInput = el('presetImportInput');
    if (importInput) importInput.addEventListener('change', _handleImportFile);

    // Close dropdown on outside click
    document.addEventListener('click', _handleDocClick);

    // Re-render labels when UI language changes
    document.addEventListener('sv:language-changed', () => {
        _updateTriggerLabel();
        _updateActiveIndicator();
        _renderDropdown();
    });

    // Save preset modal — Enter key
    const saveInput = el('savePresetInput');
    if (saveInput) {
        saveInput.addEventListener('keydown', e => {
            if (e.key === 'Enter') { e.preventDefault(); confirmSaveAsPreset(); }
            if (e.key === 'Escape') { const m = el('savePresetModal'); if (m) m.classList.remove('open'); }
        });
    }
}







