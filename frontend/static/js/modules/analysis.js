import { showToast, esc, escHtml } from './ui.js';

export function toggleAnalysisBody() {
    const body = document.getElementById('analysisBody');
    body.classList.toggle('hidden');
}

/**
 * Expand Band/Song Analysis (if collapsed) and scroll it into view.
 */
export function jumpToAnalysis() {
    const body = document.getElementById('analysisBody');
    const section = document.getElementById('analysisSection');
    if (body && body.classList.contains('hidden')) {
        body.classList.remove('hidden');
    }
    if (section) {
        section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    // Focus the artist input for immediate use
    setTimeout(() => {
        const input = document.getElementById('analysisArtist');
        if (input) input.focus();
    }, 400);
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

    // Audio features — GPT-estimated values
    const af = d.audio_features || {};
    const featureLabels = {
        energy: 'Energy', valence: 'Valence', danceability: 'Danceability',
        acousticness: 'Acousticness', instrumentalness: 'Instrumentalness',
        speechiness: 'Speechiness', liveness: 'Liveness', tempo: 'Tempo',
    };
    // Features that can be applied as filters (match audio-filters.js supported set)
    const filterableFeatures = new Set(['energy', 'valence', 'danceability', 'acousticness', 'tempo']);
    const afRows = Object.entries(featureLabels)
        .filter(([k]) => af[k] != null)
        .map(([k, label]) => {
            const val = af[k];
            const filterBtn = filterableFeatures.has(k)
                ? ` <button class="af-use-btn" onclick="applyAnalysisFilter('${k}', ${val})" title="Use as audio filter">⇒ Filter</button>`
                : '';
            if (k === 'tempo') {
                return `<div class="af-row">
                    <span class="af-label">${escHtml(label)}</span>
                    <span class="af-value">${val.toFixed(0)} BPM</span>${filterBtn}
                </div>`;
            }
            const pct = Math.round(val * 100);
            return `<div class="af-row">
                <span class="af-label">${escHtml(label)}</span>
                <div class="af-bar-track"><div class="af-bar-fill" style="width:${pct}%"></div></div>
                <span class="af-value">${pct}%</span>${filterBtn}
            </div>`;
        }).join('');

    // "Use All as Filters" button — only if there are filterable features
    const hasFilterable = Object.keys(af).some(k => filterableFeatures.has(k) && af[k] != null);
    const useAllBtn = hasFilterable
        ? `<button class="af-use-all-btn" onclick='applyAllAnalysisFilters(${JSON.stringify(af)})'>⇒ Use All as Filters</button>`
        : '';

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
        ${afRows ? `<div class="analysis-suggestions-header">Audio Features (GPT estimate) ${useAllBtn}</div><div class="af-grid">${afRows}</div>` : ''}
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
