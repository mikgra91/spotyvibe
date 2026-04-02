import * as State from './state.js';
import { attr, escHtml } from './ui.js';

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
            return;
        }
        listEl.innerHTML = runs.map(r => {
            const date = r.timestamp ? new Date(r.timestamp).toLocaleString() : '?';
            const trackCount = (r.tracks || []).length;
            const url = r.playlist_url
                ? `<a href="${attr(r.playlist_url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()" style="color:var(--primary)">Open playlist</a>`
                : '';
            const trackItems = (r.tracks || [])
                .map(t => `<li>${escHtml(t.artist)} — ${escHtml(t.track)}</li>`)
                .join('');
            return `<div class="history-run-item" onclick="this.classList.toggle('expanded')">
                <div class="history-run-header">
                    <div>
                        <div class="history-run-date">${escHtml(date)}</div>
                        <div class="history-run-info">${trackCount} track(s) added ${url}</div>
                    </div>
                    <span class="history-run-chevron">▸</span>
                </div>
                ${trackItems ? `<ul class="history-run-tracks">${trackItems}</ul>` : ''}
            </div>`;
        }).join('');
    } catch (e) {
        listEl.innerHTML = '<p style="color:var(--error)">Failed to load history.</p>';
    }
}

