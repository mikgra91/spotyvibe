import { showToast, esc, escHtml } from './ui.js';
import { i18n } from './i18n.js';

export function toggleAnalysisBody() {
    const body = document.getElementById('analysisBody');
    body.classList.toggle('hidden');
    const expanded = (!body.classList.contains('hidden')).toString();
    const header = document.querySelector('#analysisSection > .train-header');
    if (header) header.setAttribute('aria-expanded', expanded);
    const btn = document.getElementById('analysisToggleBtn');
    if (btn) {
        btn.setAttribute('aria-expanded', expanded);
        btn.textContent = expanded === 'true' ? i18n('btn.hide', 'Hide') : i18n('btn.show', 'Show');
    }
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
        section.scrollIntoView({ behavior: 'smooth', block: 'center' });
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
        resultDiv.innerHTML = `<p style="color:var(--error)">${escHtml(i18n('analysis.artist_required', 'Artist name is required.'))}</p>`;
        resultDiv.classList.remove('hidden');
        return;
    }

    btn.disabled = true;
    btn.textContent = i18n('analysis.analysing', 'Analysing…');
    resultDiv.innerHTML = `<p style="color:var(--text-secondary)">${escHtml(i18n('analysis.analysing', 'Analysing…'))}</p>`;
    resultDiv.classList.remove('hidden');

    try {
        const resp = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ artist, track }),
        });
        const data = await resp.json();
        if (!resp.ok) {
            resultDiv.innerHTML = '<p style="color:var(--error)">' + escHtml(data.error || i18n('msg.error_prefix', 'Error')) + '</p>';
            return;
        }
        resultDiv.innerHTML = renderAnalysisResult(data);
    } catch (e) {
        resultDiv.innerHTML = '<p style="color:var(--error)">' + escHtml(i18n('msg.network_error', 'Network error: {detail}').replace('{detail}', e.message)) + '</p>';
    } finally {
        btn.disabled = false;
        btn.textContent = i18n('btn.analyse', 'Analyse');
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
        energy: i18n('analysis.energy', 'Energy'), valence: i18n('analysis.valence', 'Valence'), danceability: i18n('analysis.danceability', 'Danceability'),
        acousticness: i18n('analysis.acousticness', 'Acousticness'), instrumentalness: i18n('analysis.instrumentalness', 'Instrumentalness'),
        speechiness: i18n('analysis.speechiness', 'Speechiness'), liveness: i18n('analysis.liveness', 'Liveness'), tempo: i18n('analysis.tempo', 'Tempo'),
    };
    const featureDescs = {
        energy: i18n('analysis.energy_desc', 'How intense and active the track feels.'),
        valence: i18n('analysis.valence_desc', 'Musical positiveness — happy vs. sad.'),
        danceability: i18n('analysis.danceability_desc', 'How suitable for dancing based on tempo and rhythm.'),
        acousticness: i18n('analysis.acousticness_desc', 'How acoustic a track sounds.'),
        instrumentalness: i18n('analysis.instrumentalness_desc', 'Whether a track contains vocals.'),
        speechiness: i18n('analysis.speechiness_desc', 'How much spoken word is present.'),
        liveness: i18n('analysis.liveness_desc', 'Whether the track sounds like a live performance.'),
        tempo: i18n('analysis.tempo_desc', 'The speed of the track in BPM.'),
    };
    // Features that can be applied as filters (match audio-filters.js supported set)
    const filterableFeatures = new Set(['energy', 'valence', 'danceability', 'acousticness', 'tempo']);
    const afRows = Object.entries(featureLabels)
        .filter(([k]) => af[k] != null)
        .map(([k, label]) => {
            const val = af[k];
            const desc = featureDescs[k] || '';
            const tooltipAttr = desc ? ` data-tooltip="${escHtml(desc)}"` : '';
            const filterBtn = filterableFeatures.has(k)
                ? ` <button class="af-use-btn" onclick="applyAnalysisFilter('${k}', ${val})" title="${escHtml(i18n('analysis.use_as_filter_title', 'Use as audio filter'))}">${escHtml(i18n('analysis.use_as_filter', '⇒ Filter'))}</button>`
                : '';
            if (k === 'tempo') {
                return `<div class="af-row">
                    <span class="af-label af-label-tip"${tooltipAttr}>${escHtml(label)}</span>
                    <span class="af-value">${val.toFixed(0)} BPM</span>${filterBtn}
                </div>`;
            }
            const pct = Math.round(val * 100);
            return `<div class="af-row">
                <span class="af-label af-label-tip"${tooltipAttr}>${escHtml(label)}</span>
                <div class="af-bar-track"><div class="af-bar-fill" style="width:${pct}%"></div></div>
                <span class="af-value">${pct}%</span>${filterBtn}
            </div>`;
        }).join('');

    // "Use All as Filters" button — only if there are filterable features
    const hasFilterable = Object.keys(af).some(k => filterableFeatures.has(k) && af[k] != null);
    const useAllBtn = hasFilterable
        ? `<button class="af-use-all-btn" onclick='applyAllAnalysisFilters(${JSON.stringify(af)})'>${escHtml(i18n('analysis.use_all_filters', '⇒ Use All as Filters'))}</button>`
        : '';

    const suggestions = (d.profile_suggestions || []).map((s, i) =>
        `<div class="analysis-suggestion">
            <span>${escHtml(s)}</span>
            <button class="btn-copy-suggestion" onclick="copySuggestion(${i})" data-suggestion="${escHtml(s).replace(/"/g, '&quot;')}" title="Copy to clipboard">📋</button>
        </div>`
    ).join('');

    return `<div class="analysis-card">
        <div class="analysis-title">${escHtml(d.artist)}${d.track ? ' — ' + escHtml(d.track) : ''}</div>
        <div class="analysis-row"><strong>${escHtml(i18n('analysis.genre', 'Genre:'))}</strong> ${escHtml(genres)}</div>
        <div class="analysis-row">${tags}</div>
        ${charRows ? `<table class="analysis-ch-table">${charRows}</table>` : ''}
        ${afRows ? `<div class="analysis-suggestions-header">${escHtml(i18n('analysis.audio_features_header', 'Audio Features (GPT estimate)'))} ${useAllBtn}</div><div class="af-grid">${afRows}</div>` : ''}
        ${suggestions ? `<div class="analysis-suggestions-header">${escHtml(i18n('analysis.profile_suggestions', 'Profile Suggestions (click 📋 to copy)'))}</div>${suggestions}` : ''}
    </div>`;
}

export function copySuggestion(idx) {
    const btns = document.querySelectorAll('.btn-copy-suggestion');
    const btn = btns[idx];
    const text = btn ? btn.getAttribute('data-suggestion') : '';
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => showToast(i18n('msg.copied', 'Copied to clipboard!'), 'success', 1800));
}
