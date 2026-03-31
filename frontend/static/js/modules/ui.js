export function showStatus(msg, type) {
    const box = document.getElementById('statusBox');
    box.className = `status ${type}`;
    box.textContent = msg;
    box.classList.remove('hidden');
}

export function showStatusHtml(html, type) {
    const box = document.getElementById('statusBox');
    box.className = `status ${type}`;
    box.innerHTML = html;
    box.classList.remove('hidden');
}

export function showPlaylistLink(url) {
    const box = document.getElementById('playlistLinkBox');
    box.innerHTML = `🎶 <strong>Playlist:</strong> <a href="${attr(url)}" target="_blank" rel="noopener">${esc(url)}</a>`;
    box.classList.remove('hidden');
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
    const ALLOWED_ATTRS = {A:['href','title'],IMG:['src','alt','title'],TD:['colspan','rowspan'],TH:['colspan','rowspan']};
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
}

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
