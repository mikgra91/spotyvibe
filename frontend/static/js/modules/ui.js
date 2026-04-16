import { i18n } from './i18n.js';

export function showStatus(msg, type) {
    const box = document.getElementById('statusBox');
    box.className = `status ${type}`;
    box.textContent = msg;
    // During generation, only the inline loading area shows progress;
    // the statusBox is hidden to avoid duplication.  Show it for
    // terminal states (success, error) so the final message persists.
    const loadArea = document.getElementById('generateLoadingArea');
    const isGenerating = loadArea && !loadArea.classList.contains('hidden');
    if (isGenerating && type === 'info') {
        box.classList.add('hidden');
    } else {
        box.classList.remove('hidden');
        // Ensure track area is visible so the status box can be seen
        const trackArea = document.getElementById('discoverTrackArea');
        if (trackArea) trackArea.classList.remove('hidden');
    }
    // Mirror into inline loading message area if visible
    const loadMsg = document.getElementById('generateLoadingMsg');
    if (loadMsg) loadMsg.textContent = msg;
}

export function showStatusHtml(html, type) {
    const box = document.getElementById('statusBox');
    box.className = `status ${type}`;
    box.innerHTML = html;
    const loadArea = document.getElementById('generateLoadingArea');
    const isGenerating = loadArea && !loadArea.classList.contains('hidden');
    if (isGenerating && type === 'info') {
        box.classList.add('hidden');
    } else {
        box.classList.remove('hidden');
        const trackArea = document.getElementById('discoverTrackArea');
        if (trackArea) trackArea.classList.remove('hidden');
    }
    const loadMsg = document.getElementById('generateLoadingMsg');
    if (loadMsg) loadMsg.innerHTML = html;
}

export function showPlaylistLink(url) {
    const box = document.getElementById('playlistLinkBox');
    box.innerHTML = `🎶 <strong>${i18n('generate.title', 'Playlist')}:</strong> <a href="${attr(url)}" target="_blank" rel="noopener">${esc(url)}</a>`;
    box.classList.remove('hidden');
    // Ensure track area is visible
    const trackArea = document.getElementById('discoverTrackArea');
    if (trackArea) trackArea.classList.remove('hidden');
}

export function hidePlaylistLink() {
    document.getElementById('playlistLinkBox').classList.add('hidden');
}

export function esc(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
}

export function attr(s) {
    return (s || '').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

export function sanitizeHtml(html) {
    const ALLOWED = new Set(['H1','H2','H3','H4','H5','H6','P','UL','OL','LI',
        'A','STRONG','EM','CODE','PRE','BR','HR','TABLE','THEAD','TBODY','TR',
        'TH','TD','BLOCKQUOTE','IMG','SPAN','DIV','DL','DT','DD','SUP','SUB']);
    const ALLOWED_ATTRS = {A:['href','title'],IMG:['src','alt','title'],TD:['colspan','rowspan'],TH:['colspan','rowspan'],H1:['id'],H2:['id'],H3:['id'],H4:['id'],H5:['id'],H6:['id']};
    const tmp = document.createElement('div');
    tmp.innerHTML = html;
    (function walk(parent) {
        for (const node of Array.from(parent.childNodes)) {
            if (node.nodeType === 1) {
                if (!ALLOWED.has(node.tagName)) { node.remove(); continue; }
                const ok = ALLOWED_ATTRS[node.tagName] || [];
                for (const a of Array.from(node.attributes)) {
                    if (!ok.includes(a.name) || (a.name === 'href' && /^\s*javascript:/i.test(a.value))) node.removeAttribute(a.name);
                }
                walk(node);
            }
        }
    })(tmp);
    return tmp.innerHTML;
}

export function escHtml(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

export function toggleSettingsMenu() {
    const dd = document.getElementById('settingsDropdown');
    dd.classList.toggle('open');
    const btn = document.querySelector('.burger-btn');
    if (btn) btn.setAttribute('aria-expanded', dd.classList.contains('open'));

    // F.2: Close profile dropdown/menu when burger opens (mutual-exclusion)
    if (dd.classList.contains('open')) {
        _closeAllPopovers('settingsDropdown');
    }
}

/** Close any open popovers except the one identified by `exceptId` */
function _closeAllPopovers(exceptId) {
    // Profile custom dropdown
    const profileList = document.getElementById('profileDropdownList');
    const profileDropdown = document.getElementById('profileCustomDropdown');
    if (profileList && !profileList.classList.contains('hidden') && exceptId !== 'profileCustomDropdown') {
        profileList.classList.add('hidden');
        if (profileDropdown) profileDropdown.setAttribute('aria-expanded', 'false');
    }

    // Profile context menu (⋯)
    const profileMenu = document.getElementById('profileMenuDropdown');
    const profileMenuTrigger = document.getElementById('profileMenuTrigger');
    if (profileMenu && !profileMenu.classList.contains('hidden') && exceptId !== 'profileMenuDropdown') {
        profileMenu.classList.add('hidden');
        if (profileMenuTrigger) profileMenuTrigger.setAttribute('aria-expanded', 'false');
    }

    // Settings/burger dropdown
    const settingsDD = document.getElementById('settingsDropdown');
    if (settingsDD && settingsDD.classList.contains('open') && exceptId !== 'settingsDropdown') {
        settingsDD.classList.remove('open');
        const btn = document.querySelector('.burger-btn');
        if (btn) btn.setAttribute('aria-expanded', 'false');
    }
}

export { _closeAllPopovers as closeAllPopovers };

let toastTimer = null;
export function showToast(message, type = 'success', duration = 3000) {
    const toast = document.getElementById('toast');
    if (toastTimer) clearTimeout(toastTimer);
    toast.textContent = message;
    toast.className = `toast toast-${type} show`;
    toastTimer = setTimeout(() => {
        toast.classList.remove('show');
        toastTimer = null;
    }, duration);
}

/**
 * Custom confirm dialog — replacement for native confirm() which
 * may be blocked or styled inconsistently in Android WebViews.
 * Returns a Promise<boolean>.
 */
export function showConfirm(message) {
    return new Promise((resolve) => {
        // Remove any existing confirm overlay
        const existing = document.getElementById('customConfirmOverlay');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.id = 'customConfirmOverlay';
        overlay.className = 'modal-overlay open';
        overlay.style.zIndex = '10000';
        overlay.setAttribute('role', 'alertdialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('aria-label', i18n('confirm.title', 'Confirmation'));

        const modal = document.createElement('div');
        modal.className = 'modal';
        modal.style.maxWidth = '420px';

        const msg = document.createElement('p');
        msg.style.cssText = 'white-space: pre-line; margin-bottom: 1.2rem; color: var(--text-secondary); line-height: 1.5;';
        msg.textContent = message;

        const actions = document.createElement('div');
        actions.className = 'modal-actions';

        const confirmBtn = document.createElement('button');
        confirmBtn.className = 'btn btn-save';
        confirmBtn.textContent = i18n('msg.ok', 'OK');
        confirmBtn.onclick = () => { document.removeEventListener('keydown', onKey); overlay.remove(); resolve(true); };

        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'btn btn-cancel';
        cancelBtn.textContent = i18n('btn.cancel', 'Cancel');
        cancelBtn.onclick = () => { document.removeEventListener('keydown', onKey); overlay.remove(); resolve(false); };

        actions.append(confirmBtn, cancelBtn);
        modal.append(msg, actions);
        overlay.appendChild(modal);
        document.body.appendChild(overlay);

        // Focus the confirm button
        requestAnimationFrame(() => confirmBtn.focus());

        // Close on Escape
        const onKey = (e) => {
            if (e.key === 'Escape') { document.removeEventListener('keydown', onKey); overlay.remove(); resolve(false); }
        };
        document.addEventListener('keydown', onKey);
    });
}

/**
 * Custom alert — replacement for native alert().
 * Shows a toast for simple messages, or a modal for longer error messages.
 */
export function showAlert(message, type = 'error') {
    showToast(message, type, 5000);
}
