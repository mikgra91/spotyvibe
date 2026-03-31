import * as State from './state.js';
import { showToast, attr, escHtml } from './ui.js';

export async function toggleHistoryBody() {
    const body = document.getElementById('historyBody');
    State.setHistoryBodyOpen(!State.historyBodyOpen);
    body.classList.toggle('hidden', !State.historyBodyOpen);
    if (State.historyBodyOpen) await loadHistory();
}

export async function loadHistory() {
    const listEl = document.getElementById('historyList');
    listEl.innerHTML = '<p style="color:var(--text-muted)">Loading…</p>';
    try {
        const resp = await fetch('/api/runs');
        const data = await resp.json();
        const runs = data.runs || [];
        if (runs.length === 0) {
            listEl.innerHTML = '<p style="color:var(--text-muted)">No runs yet.</p>';
            document.getElementById('undoLastRunBtn').style.display = 'none';
            return;
        }
        document.getElementById('undoLastRunBtn').style.display = '';
        listEl.innerHTML = runs.map(r => {
            const date = r.timestamp ? new Date(r.timestamp).toLocaleString() : '?';
            const trackCount = (r.tracks || []).length;
            const url = r.playlist_url ? `<a href="${attr(r.playlist_url)}" target="_blank" rel="noopener" style="color:var(--primary)">Open playlist</a>` : '';
            return `<div class="history-run-item">
                <div class="history-run-date">${escHtml(date)}</div>
                <div class="history-run-info">${trackCount} track(s) added ${url}</div>
            </div>`;
        }).join('');
    } catch (e) {
        listEl.innerHTML = '<p style="color:var(--error)">Failed to load history.</p>';
    }
}

export async function undoLastRun() {
    if (!confirm('Remove tracks added by the last run from Spotify?')) return;
    const btn = document.getElementById('undoLastRunBtn');
    btn.disabled = true;
    try {
        const resp = await fetch('/api/runs/undo', { method: 'POST' });
        const data = await resp.json();
        if (resp.ok) {
            showToast(`✅ Removed ${data.removed} track(s) from Spotify.`, 'success', 3000);
            await loadHistory();
        } else {
            alert('Error: ' + (data.error || 'Unknown error'));
        }
    } catch (e) {
        alert('Network error: ' + e.message);
    } finally {
        btn.disabled = false;
    }
}
