/**
 * rationale.js — Chip rendering for track rationale (Wave 3 D.3)
 */
import { i18n } from './i18n.js';

const defaultTemplateByType = {
    profile_match: "matches '{arg}'",
    artist_match: "similar to {arg}",
    recency: "{arg}",
    novelty: "{arg}",
    audio_match: "matches {arg}",
    legacy: "{arg}",
    fallback: "profile match",
};

function truncate(str, max) {
    if (!str) return '';
    return str.length > max ? str.slice(0, max) + '…' : str;
}

function renderChip(chip) {
    const type = chip.type || 'fallback';
    const templateKey = 'explain.' + type;
    const template = i18n(templateKey, defaultTemplateByType[type] || '{arg}');
    const label = template.replace('{arg}', truncate(chip.arg || '', 40));

    return `<span class="rationale-chip rationale-chip--${type}">
        <span class="rationale-chip-dot" aria-hidden="true"></span>
        <span class="rationale-chip-label">${label}</span>
    </span>`;
}

/**
 * Render rationale chips into a container element.
 * @param {HTMLElement} container - The .track-rationale element.
 * @param {Array} rationale - Array of {type, arg?} objects.
 */
export function renderRationale(container, rationale) {
    if (!container) return;
    if (!rationale || !Array.isArray(rationale) || rationale.length === 0) {
        rationale = [{ type: 'fallback' }];
    }
    container.innerHTML = rationale.slice(0, 2).map(renderChip).join('');
}

/**
 * Build rationale HTML string for use in buildTrackCardHtml.
 * @param {Array} rationale - Array of {type, arg?} objects.
 * @returns {string} HTML string of chips.
 */
export function buildRationaleHtml(rationale) {
    if (!rationale || !Array.isArray(rationale) || rationale.length === 0) {
        rationale = [{ type: 'fallback' }];
    }
    return rationale.slice(0, 2).map(renderChip).join('');
}

/**
 * Find all .track-rationale elements with data-track-rationale attributes
 * and render chips into them.
 */
export function renderAll() {
    document.querySelectorAll('.track-rationale[data-track-rationale]').forEach(el => {
        try {
            const data = el.getAttribute('data-track-rationale');
            if (data) {
                const rationale = JSON.parse(data);
                renderRationale(el, rationale);
            }
        } catch (e) {
            // Silently skip malformed data
        }
    });
}

export function init() {
    renderAll();
}

