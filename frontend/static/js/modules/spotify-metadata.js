import * as State from './state.js';
import { escHtml } from './ui.js';

export function toggleSpotifyMetadata() {
    const body = document.getElementById('spotifyMetadataBody');
    const btn = document.getElementById('spotifyMetaToggleBtn');
    const isHidden = body.classList.contains('hidden');
    body.classList.toggle('hidden', !isHidden);
    btn.textContent = isHidden ? 'Close' : 'Open';
}

export async function runSpotifyMetadata() {
    const artist = (document.getElementById('spotifyMetaArtist').value || '').trim();
    const track = (document.getElementById('spotifyMetaTrack').value || '').trim();
    const market = (document.getElementById('spotifyMetaMarket').value || 'US').trim().toUpperCase().slice(0, 2) || 'US';

    const errEl = document.getElementById('spotifyMetaError');
    const loadEl = document.getElementById('spotifyMetaLoading');
    const resultEl = document.getElementById('spotifyMetaResult');
    const btn = document.getElementById('spotifyMetaAnalyseBtn');

    if (!artist && !track) {
        errEl.textContent = 'Enter at least an artist or track name.';
        errEl.classList.remove('hidden');
        return;
    }

    errEl.classList.add('hidden');
    resultEl.classList.add('hidden');
    loadEl.classList.remove('hidden');
    btn.disabled = true;

    try {
        const resp = await fetch('/api/spotify/metadata/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ artist: artist || undefined, track: track || undefined, market }),
        });
        const data = await resp.json();

        if (!resp.ok) {
            errEl.textContent = data.error || 'Analysis failed.';
            errEl.classList.remove('hidden');
            return;
        }

        resultEl.innerHTML = renderMetadataResult(data);
        resultEl.classList.remove('hidden');
    } catch (e) {
        errEl.textContent = 'Network error: ' + e.message;
        errEl.classList.remove('hidden');
    } finally {
        loadEl.classList.add('hidden');
        btn.disabled = false;
    }
}

function renderMetadataResult(data) {
    const parts = [];

    // Match summary
    if (data.match) {
        const m = data.match;
        const conf = m.confidence != null ? Math.round(m.confidence * 100) + '%' : '—';
        const confClass = m.confidence >= 0.8 ? 'confidence-high' : m.confidence >= 0.5 ? 'confidence-mid' : 'confidence-low';
        parts.push(`<div class="meta-block meta-match">
            <div class="meta-block-title">Match Summary</div>
            <div class="meta-grid">
                <span class="meta-key">Type</span><span class="meta-val">${escHtml(m.type || '—')}</span>
                <span class="meta-key">Confidence</span><span class="meta-val"><span class="confidence-badge ${escHtml(confClass)}">${escHtml(conf)}</span></span>
                ${m.spotify_track_id ? `<span class="meta-key">Track ID</span><span class="meta-val meta-id">${escHtml(m.spotify_track_id)}</span>` : ''}
                ${m.spotify_artist_id ? `<span class="meta-key">Artist ID</span><span class="meta-val meta-id">${escHtml(m.spotify_artist_id)}</span>` : ''}
            </div>
        </div>`);
    }

    // Track metadata
    if (data.track) {
        const t = data.track;
        const artists = Array.isArray(t.artists) ? t.artists.join(', ') : (t.artists || '—');
        const dur = t.duration_ms ? formatDuration(t.duration_ms) : '—';
        parts.push(`<div class="meta-block meta-track">
            <div class="meta-block-title">Track</div>
            <div class="meta-grid">
                <span class="meta-key">Name</span><span class="meta-val">${escHtml(t.name || '—')}</span>
                <span class="meta-key">Artists</span><span class="meta-val">${escHtml(artists)}</span>
                <span class="meta-key">Album</span><span class="meta-val">${escHtml(t.album || '—')}</span>
                <span class="meta-key">Released</span><span class="meta-val">${escHtml(t.release_date || '—')}</span>
                <span class="meta-key">Duration</span><span class="meta-val">${escHtml(dur)}</span>
                <span class="meta-key">Popularity</span><span class="meta-val">${t.popularity != null ? escHtml(String(t.popularity)) + '/100' : '—'}</span>
                ${t.external_urls && t.external_urls.spotify ? `<span class="meta-key">Spotify</span><span class="meta-val"><a href="${escHtml(t.external_urls.spotify)}" target="_blank" rel="noopener" style="color:var(--primary)">Open ↗</a></span>` : ''}
            </div>
        </div>`);
    }

    // Artist metadata
    if (data.artist) {
        const a = data.artist;
        const genres = Array.isArray(a.genres) && a.genres.length ? a.genres.slice(0,5).join(', ') : '—';
        const followers = a.followers != null ? Number(a.followers).toLocaleString() : '—';
        parts.push(`<div class="meta-block meta-artist">
            <div class="meta-block-title">Artist</div>
            <div class="meta-grid">
                <span class="meta-key">Name</span><span class="meta-val">${escHtml(a.name || '—')}</span>
                <span class="meta-key">Genres</span><span class="meta-val">${escHtml(genres)}</span>
                <span class="meta-key">Popularity</span><span class="meta-val">${a.popularity != null ? escHtml(String(a.popularity)) + '/100' : '—'}</span>
                <span class="meta-key">Followers</span><span class="meta-val">${escHtml(followers)}</span>
                ${a.external_urls && a.external_urls.spotify ? `<span class="meta-key">Spotify</span><span class="meta-val"><a href="${escHtml(a.external_urls.spotify)}" target="_blank" rel="noopener" style="color:var(--primary)">Open ↗</a></span>` : ''}
            </div>
        </div>`);
    }

    // Audio features
    if (data.audio_features) {
        const f = data.audio_features;
        const featureRows = [
            ['Energy', f.energy],
            ['Valence', f.valence],
            ['Danceability', f.danceability],
            ['Acousticness', f.acousticness],
            ['Instrumentalness', f.instrumentalness],
            ['Speechiness', f.speechiness],
            ['Liveness', f.liveness],
            ['Tempo', f.tempo != null ? f.tempo.toFixed(1) + ' BPM' : null],
        ].filter(([, v]) => v != null)
         .map(([k, v]) => `<span class="meta-key">${escHtml(k)}</span><span class="meta-val">${escHtml(typeof v === 'number' && v <= 1 ? (v * 100).toFixed(0) + '%' : String(v))}</span>`)
         .join('');
        parts.push(`<div class="meta-block meta-audio">
            <div class="meta-block-title">Audio Features</div>
            <div class="meta-grid">${featureRows}</div>
        </div>`);
    }

    // Warnings
    if (data.warnings && data.warnings.length) {
        const warnHtml = data.warnings.map(w => `<span class="warning-badge">${escHtml(warningLabel(w))}</span>`).join(' ');
        parts.push(`<div class="meta-block meta-warnings">
            <div class="meta-block-title">Notices</div>
            <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:6px;">${warnHtml}</div>
        </div>`);
    }

    return `<div class="metadata-result">${parts.join('')}</div>`;
}

function formatDuration(ms) {
    const s = Math.floor(ms / 1000);
    return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
}

function warningLabel(w) {
    const labels = {
        'low_confidence_match': 'Low confidence match',
        'audio_features_unavailable': 'Audio features unavailable',
    };
    return labels[w] || w;
}

// Provider summary pill rendering
export function renderProviderPills() {
    renderOpenaiPills();
    renderSpotifyPills();
    renderDepChips();
}

function renderOpenaiPills() {
    const el = document.getElementById('openaiStatusPills');
    if (!el) return;
    const pills = [];
    pills.push(pill(State.openaiKeySet ? 'ok' : 'err', State.openaiKeySet ? 'Key configured' : 'Key missing'));
    pills.push(pill(State.profileTrained ? 'ok' : 'warn', State.profileTrained ? 'Profile trained' : 'Not trained'));
    el.innerHTML = pills.join('');
}

function renderSpotifyPills() {
    const el = document.getElementById('spotifyStatusPills');
    if (!el) return;
    const pills = [];
    const authStatus = State.spotifyAuthStatus;
    if (authStatus === 'authenticated') {
        pills.push(pill('ok', 'Connected'));
    } else if (authStatus === 'not_authenticated') {
        pills.push(pill('warn', 'Not connected'));
    } else if (authStatus === 'not_configured') {
        pills.push(pill('err', 'Credentials missing'));
    } else {
        pills.push(pill('warn', 'Status unknown'));
    }
    el.innerHTML = pills.join('');
}

function renderDepChips() {
    const openaiDot = document.querySelector('#depOpenai .dep-dot');
    const spotifyDot = document.querySelector('#depSpotify .dep-dot');
    if (openaiDot) {
        const ok = State.openaiKeySet && State.profileTrained;
        openaiDot.className = 'dep-dot ' + (ok ? 'dep-dot--ok' : 'dep-dot--warn');
    }
    if (spotifyDot) {
        const ok = State.spotifyAuthStatus === 'authenticated';
        spotifyDot.className = 'dep-dot ' + (ok ? 'dep-dot--ok' : 'dep-dot--warn');
    }
}

function pill(type, label) {
    return `<span class="status-pill status-pill--${type}">${escHtml(label)}</span>`;
}
