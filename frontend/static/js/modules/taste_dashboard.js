/**
 * taste_dashboard.js — Taste visualisation dashboard (Wave 3 F.1)
 * Custom SVG charts: donut, scatter, bar. No chart library.
 */
import { i18n } from './i18n.js';

const CHART_COLOURS = [
    'var(--primary)', 'var(--accent-teal, #2dd4bf)', 'var(--accent-cyan, #22d3ee)',
    'var(--accent-purple, #a78bfa)', 'var(--accent-pink, #f472b6)',
    'var(--accent-violet, #8b5cf6)', '#1ed760', 'var(--text-muted)',
];

let _loaded = false;
let _tooltipEl = null;

function _ensureTooltip() {
    if (!_tooltipEl) {
        _tooltipEl = document.createElement('div');
        _tooltipEl.className = 'dashboard-tooltip';
        _tooltipEl.style.display = 'none';
        document.body.appendChild(_tooltipEl);
    }
    return _tooltipEl;
}

function _showTooltip(e, text) {
    const tip = _ensureTooltip();
    tip.textContent = text;
    tip.style.display = 'block';
    tip.style.left = (e.clientX + 12) + 'px';
    tip.style.top = (e.clientY - 10) + 'px';
}

function _hideTooltip() {
    const tip = _ensureTooltip();
    tip.style.display = 'none';
}

/* ── Donut chart ─────────────────────────────────────────────────── */
function renderDonut(container, genres) {
    const total = genres.reduce((s, g) => s + g.count, 0);
    if (total === 0) return;

    const size = 200, cx = 100, cy = 100, outerR = 90, innerR = 36;
    let svg = `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" role="img">`;
    svg += `<title>${i18n('dashboard.card_genres', 'Top genres')}</title>`;

    let startAngle = -Math.PI / 2;
    genres.forEach((g, i) => {
        const slice = (g.count / total) * 2 * Math.PI;
        const endAngle = startAngle + slice;
        const largeArc = slice > Math.PI ? 1 : 0;

        const x1 = cx + outerR * Math.cos(startAngle);
        const y1 = cy + outerR * Math.sin(startAngle);
        const x2 = cx + outerR * Math.cos(endAngle);
        const y2 = cy + outerR * Math.sin(endAngle);
        const ix1 = cx + innerR * Math.cos(endAngle);
        const iy1 = cy + innerR * Math.sin(endAngle);
        const ix2 = cx + innerR * Math.cos(startAngle);
        const iy2 = cy + innerR * Math.sin(startAngle);

        const d = `M${x1},${y1} A${outerR},${outerR} 0 ${largeArc},1 ${x2},${y2} L${ix1},${iy1} A${innerR},${innerR} 0 ${largeArc},0 ${ix2},${iy2} Z`;
        svg += `<path d="${d}" fill="${CHART_COLOURS[i % CHART_COLOURS.length]}" data-genre="${g.genre}" data-count="${g.count}" role="button" aria-label="${g.genre}, ${g.count} tracks" style="cursor:pointer"/>`;
        startAngle = endAngle;
    });
    svg += `</svg>`;

    // Legend
    let legend = '<div class="dashboard-legend">';
    genres.forEach((g, i) => {
        legend += `<div class="dashboard-legend-row">
            <span class="legend-swatch" style="background:${CHART_COLOURS[i % CHART_COLOURS.length]}"></span>
            <span>${g.genre}</span><span style="margin-left:auto">${g.count}</span>
        </div>`;
    });
    legend += '</div>';

    container.innerHTML = `<h4>${i18n('dashboard.card_genres', 'Top genres')}</h4>${svg}${legend}`;

    // Tooltip on hover
    container.querySelectorAll('path[data-genre]').forEach(path => {
        path.addEventListener('pointermove', e => _showTooltip(e, `${path.dataset.genre} — ${path.dataset.count} tracks`));
        path.addEventListener('pointerleave', _hideTooltip);
    });
}

/* ── Scatter chart ───────────────────────────────────────────────── */
function renderScatter(container, points) {
    const w = 260, h = 220, pad = 35;
    let svg = `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img">`;
    svg += `<title>${i18n('dashboard.card_scatter', 'Energy × valence')}</title>`;

    // Axes
    svg += `<line x1="${pad}" y1="${h - pad}" x2="${w - 10}" y2="${h - pad}" stroke="var(--border)" stroke-width="1"/>`;
    svg += `<line x1="${pad}" y1="10" x2="${pad}" y2="${h - pad}" stroke="var(--border)" stroke-width="1"/>`;

    // Labels
    svg += `<text x="${pad}" y="${h - 5}" font-size="9" fill="var(--text-muted)">${i18n('dashboard.scatter_sad', 'Sad')}</text>`;
    svg += `<text x="${w - 40}" y="${h - 5}" font-size="9" fill="var(--text-muted)">${i18n('dashboard.scatter_happy', 'Happy')}</text>`;
    svg += `<text x="3" y="${h - pad - 5}" font-size="9" fill="var(--text-muted)" transform="rotate(-90, 10, ${h - pad - 5})">${i18n('dashboard.scatter_calm', 'Calm')}</text>`;
    svg += `<text x="3" y="20" font-size="9" fill="var(--text-muted)" transform="rotate(-90, 10, 20)">${i18n('dashboard.scatter_intense', 'Intense')}</text>`;

    const chartW = w - pad - 10;
    const chartH = h - pad - 10;

    points.forEach(p => {
        const x = pad + p.valence * chartW;
        const y = (h - pad) - p.energy * chartH;
        svg += `<circle cx="${x}" cy="${y}" r="4" fill="var(--primary)" fill-opacity="0.6" stroke="var(--primary)" stroke-opacity="0.9" stroke-width="1" data-artist="${p.artist}" data-title="${p.title}" style="cursor:pointer"/>`;
    });
    svg += `</svg>`;

    container.innerHTML = `<h4>${i18n('dashboard.card_scatter', 'Energy × valence')}</h4>${svg}`;

    container.querySelectorAll('circle[data-artist]').forEach(circle => {
        circle.addEventListener('pointermove', e => _showTooltip(e, `${circle.dataset.artist} — ${circle.dataset.title}`));
        circle.addEventListener('pointerleave', _hideTooltip);
    });
}

/* ── Bar chart ───────────────────────────────────────────────────── */
function renderBars(container, decades) {
    const w = 260, h = 180, pad = 35;
    const n = decades.length;
    if (n === 0) return;

    const maxCount = Math.max(...decades.map(d => d.count));
    const gap = 6;
    const barW = Math.max(12, (w - pad - 10 - (n - 1) * gap) / n);
    const chartH = h - pad - 20;

    let svg = `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img">`;
    svg += `<title>${i18n('dashboard.card_decades', 'Decades')}</title>`;

    // X axis
    svg += `<line x1="${pad}" y1="${h - pad}" x2="${w - 10}" y2="${h - pad}" stroke="var(--border)" stroke-width="1"/>`;

    decades.forEach((d, i) => {
        const barH = maxCount > 0 ? (d.count / maxCount) * chartH : 0;
        const x = pad + i * (barW + gap);
        const y = h - pad - barH;
        svg += `<rect x="${x}" y="${y}" width="${barW}" height="${barH}" rx="2" ry="2" fill="var(--primary)" fill-opacity="0.85" data-decade="${d.decade}" data-count="${d.count}" style="cursor:pointer"/>`;
        svg += `<text x="${x + barW / 2}" y="${h - pad + 14}" font-size="8" fill="var(--text-muted)" text-anchor="middle">${d.decade}</text>`;
    });
    svg += `</svg>`;

    container.innerHTML = `<h4>${i18n('dashboard.card_decades', 'Decades')}</h4>${svg}`;

    container.querySelectorAll('rect[data-decade]').forEach(rect => {
        rect.addEventListener('pointermove', e => _showTooltip(e, `${rect.dataset.decade} — ${rect.dataset.count} tracks`));
        rect.addEventListener('pointerleave', _hideTooltip);
    });
}

/* ── Main ────────────────────────────────────────────────────────── */
async function loadDashboard() {
    if (_loaded) return;
    const grid = document.querySelector('.dashboard-grid');
    const empty = document.querySelector('.dashboard-empty');
    if (!grid) return;

    try {
        const resp = await fetch('/api/taste/aggregate');
        const data = await resp.json();

        if (data.tracks_considered < 10) {
            grid.classList.add('hidden');
            if (empty) empty.classList.remove('hidden');
            return;
        }

        grid.classList.remove('hidden');
        if (empty) empty.classList.add('hidden');

        const genreCard = grid.querySelector('.dashboard-card--genres');
        const scatterCard = grid.querySelector('.dashboard-card--scatter');
        const decadesCard = grid.querySelector('.dashboard-card--decades');

        if (genreCard && data.top_genres) renderDonut(genreCard, data.top_genres);
        if (scatterCard && data.energy_valence) renderScatter(scatterCard, data.energy_valence);
        if (decadesCard && data.decades) renderBars(decadesCard, data.decades);

        _loaded = true;
    } catch (e) {
        console.warn('Dashboard load failed:', e);
    }
}

export function init() {
    const header = document.querySelector('.taste-dashboard-section .accordion-header');
    if (!header) return;

    // Restore open/closed state
    const section = document.querySelector('.taste-dashboard-section');
    const body = section ? section.querySelector('.accordion-body') : null;
    const isOpen = localStorage.getItem('sv.dashboard_open') !== 'false';

    if (body) {
        body.classList.toggle('hidden', !isOpen);
        if (isOpen) loadDashboard();
    }

    header.addEventListener('click', () => {
        if (!body) return;
        const nowHidden = body.classList.toggle('hidden');
        localStorage.setItem('sv.dashboard_open', (!nowHidden).toString());
        if (!nowHidden) loadDashboard();

        const chevron = header.querySelector('.accordion-chevron');
        if (chevron) chevron.classList.toggle('rotated', !nowHidden);
    });
}

