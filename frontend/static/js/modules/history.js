import * as State from './state.js';
import { attr, escHtml } from './ui.js';
import { i18n } from './i18n.js';
import { buildRationaleHtml } from './rationale.js';

export async function toggleHistoryBody() {
    const body = document.getElementById('historyBody');
    State.setHistoryBodyOpen(!State.historyBodyOpen);
    body.classList.toggle('hidden', !State.historyBodyOpen);
    const expanded = State.historyBodyOpen.toString();
    const header = document.querySelector('#historySection > .train-header');
    if (header) header.setAttribute('aria-expanded', expanded);
    document.querySelectorAll('#historySection .train-header-actions button[aria-controls]').forEach(
        btn => btn.setAttribute('aria-expanded', expanded)
    );
    const toggleBtn = document.getElementById('historyToggleBtn');
    if (toggleBtn) toggleBtn.textContent = State.historyBodyOpen ? i18n('btn.hide', 'Hide') : i18n('btn.show', 'Show');
    if (State.historyBodyOpen) await loadHistory();
    // Wave 3: First history view tip
    if (State.historyBodyOpen && !localStorage.getItem('sv.history_viewed') && window.Tips) {
        localStorage.setItem('sv.history_viewed', '1');
        window.Tips.maybeTrigger('first_history_view');
    }
}

export async function loadHistory() {
    const listEl = document.getElementById('historyList');
    listEl.innerHTML = `<p style="color:var(--text-muted)">${i18n('msg.loading', 'Loading…')}</p>`;
    try {
        const resp = await fetch('/api/runs');
        const data = await resp.json();
        const runs = data.runs || [];
        if (runs.length === 0) {
            listEl.innerHTML = `<p style="color:var(--text-muted)">${i18n('history.no_runs', 'No runs yet.')}</p>`;
            return;
        }
        listEl.innerHTML = runs.map(r => {
            const date = r.timestamp ? new Date(r.timestamp).toLocaleString() : '?';
            const trackCount = (r.tracks || []).length;
            const url = r.playlist_url
                ? `<a href="${attr(r.playlist_url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()" style="color:var(--primary)">${i18n('history.open_playlist', 'Open playlist')}</a>`
                : '';
            const trackItems = (r.tracks || [])
                .map(t => `<li>${escHtml(t.artist)} — ${escHtml(t.track)}<div class="track-rationale">${buildRationaleHtml(t.rationale)}</div></li>`)
                .join('');
            return `<div class="history-run-item" tabindex="0" role="button" onclick="this.classList.toggle('expanded')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();this.classList.toggle('expanded')}">
                <div class="history-run-header">
                    <div>
                        <div class="history-run-date">${escHtml(date)}</div>
                        <div class="history-run-info">${trackCount} ${i18n('history.tracks_added', 'track(s) added')} ${url}</div>
                    </div>
                    <span class="history-run-chevron">▸</span>
                </div>
                ${trackItems ? `<ul class="history-run-tracks">${trackItems}</ul>` : ''}
            </div>`;
        }).join('');
    } catch (e) {
        listEl.innerHTML = `<p style="color:var(--error)">${i18n('history.load_failed', 'Failed to load history.')}</p>`;
    }
}
