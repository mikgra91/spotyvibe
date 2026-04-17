import { el } from './dom.js';
/* setup_guide.js — Owner of detail-overlay open/close, copy-to-clipboard, keyboard (Esc) */

/* i18n helper — delegates to the global i18n if available (loaded by main.js) */
function _sgI18n(key, fallback) {
    if (typeof window._i18n === 'function') return window._i18n(key, fallback);
    return fallback;
}

/**
 * Open the setup guide overlay and load guide content from the server.
 * @param {string} slug - Guide identifier (e.g., 'openai_api_key', 'spotify_developer_app')
 */
function openSetupGuide(slug) {
    const overlay = el('setupGuideOverlay');
    if (!overlay) return;

    overlay.classList.add('open');
    document.body.style.overflow = 'hidden';

    const titleEl = el('setupGuideTitle');
    const subtitleEl = el('setupGuideSubtitle');
    const stepsEl = el('setupGuideSteps');

    // Show loading state
    if (titleEl) titleEl.textContent = _sgI18n('guide.loading', 'Loading…');
    if (subtitleEl) subtitleEl.textContent = '';
    if (stepsEl) stepsEl.innerHTML = '';

    fetch('/api/help/guide/' + encodeURIComponent(slug))
        .then(resp => {
            if (!resp.ok) throw new Error('Guide not found');
            return resp.json();
        })
        .then(data => {
            if (titleEl) titleEl.textContent = data.title || '';
            if (subtitleEl) subtitleEl.textContent = data.subtitle || '';
            if (stepsEl) {
                stepsEl.innerHTML = '';
                (data.steps || []).forEach((step, i) => {
                    const li = document.createElement('li');
                    li.className = 'setup-guide-step';

                    const num = document.createElement('div');
                    num.className = 'setup-guide-step-num';
                    num.textContent = String(i + 1);

                    const body = document.createElement('div');
                    body.className = 'setup-guide-step-body';

                    const h3 = document.createElement('h3');
                    h3.className = 'setup-guide-step-title';
                    h3.textContent = step.title || '';

                    const desc = document.createElement('p');
                    desc.className = 'setup-guide-step-desc';
                    desc.innerHTML = _linkify(step.description || '');

                    body.appendChild(h3);
                    body.appendChild(desc);

                    // Optional image
                    if (step.image) {
                        const img = document.createElement('img');
                        img.className = 'setup-guide-step-img';
                        img.src = step.image;
                        img.alt = step.title || ('Step ' + (i + 1));
                        img.loading = 'lazy';
                        body.appendChild(img);
                    }

                    // Optional copy block
                    if (step.copy) {
                        const copyRow = document.createElement('div');
                        copyRow.className = 'setup-guide-step-copy';

                        const code = document.createElement('code');
                        code.textContent = step.copy;

                        const btn = document.createElement('button');
                        btn.className = 'btn-copy';
                        btn.textContent = _sgI18n('guide.copy', '📋 Copy');
                        btn.onclick = function () {
                            _copyToClipboard(step.copy, btn);
                        };

                        copyRow.appendChild(code);
                        copyRow.appendChild(btn);
                        body.appendChild(copyRow);
                    }

                    li.appendChild(num);
                    li.appendChild(body);
                    stepsEl.appendChild(li);
                });
            }
        })
        .catch(() => {
            if (titleEl) titleEl.textContent = _sgI18n('guide.error_title', 'Error loading guide');
            if (subtitleEl) subtitleEl.textContent = _sgI18n('guide.error_subtitle', 'Please try again later.');
        });
}

/**
 * Close the setup guide overlay.
 */
function closeSetupGuide() {
    const overlay = el('setupGuideOverlay');
    if (overlay) {
        overlay.classList.remove('open');
        document.body.style.overflow = '';
    }
}

/**
 * Copy text to clipboard and swap button label.
 */
function _copyToClipboard(text, btn) {
    navigator.clipboard.writeText(text).then(() => {
        const original = btn.textContent;
        btn.textContent = _sgI18n('guide.copied', '✓ Copied');
        setTimeout(() => {
            btn.textContent = original;
        }, 1500);
    }).catch(() => {
        // Fallback for older browsers
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        const original = btn.textContent;
        btn.textContent = _sgI18n('guide.copied', '✓ Copied');
        setTimeout(() => {
            btn.textContent = original;
        }, 1500);
    });
}

/**
 * Convert markdown-style links to HTML links.
 */
function _linkify(text) {
    // Escape the full text first to prevent HTML injection
    const d = document.createElement('div');
    d.textContent = text;
    const escaped = d.innerHTML;
    // Only match http:// or https:// URLs in markdown link syntax
    return escaped.replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
}

// Expose for HTML onclick= attributes (templates reference openSetupGuide)
window.openSetupGuide = openSetupGuide;
window.closeSetupGuide = closeSetupGuide;

// Event listeners — close on Esc, close button, done button, outside click
document.addEventListener('DOMContentLoaded', function () {
    const overlay = el('setupGuideOverlay');
    const closeBtn = el('setupGuideClose');
    const doneBtn = el('setupGuideDone');

    if (closeBtn) {
        closeBtn.addEventListener('click', closeSetupGuide);
    }

    if (doneBtn) {
        doneBtn.addEventListener('click', closeSetupGuide);
    }

    if (overlay) {
        overlay.addEventListener('click', function (e) {
            // Close when clicking outside the card
            if (e.target === overlay || e.target.classList.contains('setup-guide-scroll')) {
                closeSetupGuide();
            }
        });
    }

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            const overlay = el('setupGuideOverlay');
            if (overlay && overlay.classList.contains('open')) {
                e.stopImmediatePropagation();
                closeSetupGuide();
            }
        }
    });
});

