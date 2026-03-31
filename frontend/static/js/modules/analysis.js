import { showToast, esc, escHtml } from './ui.js';

export function toggleAnalysisBody() {
    const body = document.getElementById('analysisBody');
    body.classList.toggle('hidden');
}

export async function runAnalysis() {
    const artist = document.getElementById('analysisArtist').value.trim();
    const track = document.getElementById('analysisTrack').value.trim();
    const resultDiv = document.getElementById('analysisResult');
    const btn = document.getElementById('analysisSendBtn');

    if (!artist) {
        resultDiv.innerHTML = '<p style="color:var(--error)">Artist name is required.</p>';
        resultDiv.classList.remove('hidden');
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Analysing…';
    resultDiv.innerHTML = '<p style="color:var(--text-secondary)">Analysing…</p>';
    resultDiv.classList.remove('hidden');

    try {
        const resp = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ artist, track }),
        });
        const data = await resp.json();
        if (!resp.ok) {
            resultDiv.innerHTML = '<p style="color:var(--error)">' + escHtml(data.error || 'Error') + '</p>';
            return;
        }
        resultDiv.innerHTML = renderAnalysisResult(data);
    } catch (e) {
        resultDiv.innerHTML = '<p style="color:var(--error)">Network error: ' + escHtml(e.message) + '</p>';
    } finally {
        btn.disabled = false;
        btn.textContent = 'Analyse';
    }
}

export function renderAnalysisResult(d) {
    const genres = (d.genre || []).join(', ') || '—';
    const tags = (d.style_tags || []).map(t => `<span class="analysis-tag">${escHtml(t)}</span>`).join('');
    const ch = d.characteristics || {};
    const charRows = Object.entries(ch).map(([k, v]) =>
        `<tr><td class="analysis-ch-key">${escHtml(k)}</td><td>${escHtml(String(v))}</td></tr>`
    ).join('');
    const suggestions = (d.profile_suggestions || []).map((s, i) =>
        `<div class="analysis-suggestion">
            <span>${escHtml(s)}</span>
            <button class="btn-copy-suggestion" onclick="copySuggestion(${i})" data-suggestion="${escHtml(s).replace(/"/g, '&quot;')}" title="Copy to clipboard">📋</button>
        </div>`
    ).join('');

    return `<div class="analysis-card">
        <div class="analysis-title">${escHtml(d.artist)}${d.track ? ' — ' + escHtml(d.track) : ''}</div>
        <div class="analysis-row"><strong>Genre:</strong> ${escHtml(genres)}</div>
        <div class="analysis-row">${tags}</div>
        ${charRows ? `<table class="analysis-ch-table">${charRows}</table>` : ''}
        ${suggestions ? `<div class="analysis-suggestions-header">Profile Suggestions (click 📋 to copy)</div>${suggestions}` : ''}
    </div>`;
}

export function copySuggestion(idx) {
    const btns = document.querySelectorAll('.btn-copy-suggestion');
    const btn = btns[idx];
    const text = btn ? btn.getAttribute('data-suggestion') : '';
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => showToast('Copied to clipboard!', 'success', 1800));
}
