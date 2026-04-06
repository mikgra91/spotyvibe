/**
 * Quickstart guide — interactive storyboard demo player.
 *
 * Each step page (1–6) has a mini demo player with a viewport that renders
 * simplified mockups of the app UI and animates through interaction frames.
 * The user can play/pause (auto-advance) or manually step through frames.
 */
import { i18n } from './i18n.js';

/* ── Frame definitions for each step ── */

function _step1Frames() {
    return [
        {
            caption: i18n('quickstart.demo1_f1', 'Click the menu icon (☰) in the top-right corner'),
            html: `<div class="qd-scene">
                <div class="qd-bar"><span class="qd-logo">SpotyVibe</span><span class="qd-burger qd-pulse">☰</span></div>
                <div class="qd-body-placeholder"></div>
                <div class="qd-cursor" style="top:12px;right:24px"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo1_f2', 'Select "🔑 Credentials" from the dropdown'),
            html: `<div class="qd-scene">
                <div class="qd-bar"><span class="qd-logo">SpotyVibe</span><span class="qd-burger qd-active">☰</span></div>
                <div class="qd-dropdown">
                    <div class="qd-menu-item qd-pulse">🔑 Credentials</div>
                    <div class="qd-menu-item">⚙️ Settings</div>
                    <div class="qd-menu-item">🔌 Connect Spotify</div>
                    <div class="qd-menu-item">❓ Help</div>
                </div>
                <div class="qd-cursor" style="top:50px;right:40px"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo1_f3', 'Enter your API keys and click Save'),
            html: `<div class="qd-scene">
                <div class="qd-mini-modal">
                    <div class="qd-modal-title">🔑 Credentials</div>
                    <div class="qd-field"><span class="qd-label">OpenAI Key</span><span class="qd-input qd-typing">sk-abc…xyz</span></div>
                    <div class="qd-field"><span class="qd-label">Client ID</span><span class="qd-input qd-typing">a1b2c3…</span></div>
                    <div class="qd-field"><span class="qd-label">Client Secret</span><span class="qd-input qd-typing">x9y8z7…</span></div>
                    <button class="qd-btn qd-btn-primary qd-pulse">Save</button>
                </div>
                <div class="qd-cursor" style="bottom:22px;left:50%"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo1_f4', 'Connect Spotify — status pills turn green ✓'),
            html: `<div class="qd-scene">
                <div class="qd-bar"><span class="qd-logo">SpotyVibe</span><span class="qd-burger">☰</span></div>
                <div class="qd-pills-row">
                    <span class="qd-pill qd-pill-green qd-pop">✓ Key configured</span>
                    <span class="qd-pill qd-pill-green qd-pop" style="animation-delay:.15s">✓ Connected</span>
                    <span class="qd-pill qd-pill-green qd-pop" style="animation-delay:.3s">✓ Profile trained</span>
                </div>
                <div class="qd-result-msg">✅ Ready to go!</div>
            </div>`
        }
    ];
}

function _step2Frames() {
    return [
        {
            caption: i18n('quickstart.demo2_f1', 'Expand the Music Profile section'),
            html: `<div class="qd-scene">
                <div class="qd-section qd-pulse"><span class="qd-badge qd-badge-openai">OpenAI</span><span class="qd-section-title">Music Profile</span><span class="qd-chevron">▼</span></div>
                <div class="qd-body-placeholder"></div>
                <div class="qd-cursor" style="top:18px;left:50%"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo2_f2', 'Create a new profile and give it a name'),
            html: `<div class="qd-scene">
                <div class="qd-section qd-open"><span class="qd-badge qd-badge-openai">OpenAI</span><span class="qd-section-title">Music Profile</span><span class="qd-chevron">▲</span></div>
                <div class="qd-profile-area">
                    <button class="qd-btn qd-btn-outline qd-pulse">+ Create new Profile</button>
                    <div class="qd-field qd-fade-in"><span class="qd-input qd-typing">My Workout Mix</span></div>
                </div>
                <div class="qd-cursor" style="top:55px;left:50%"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo2_f3', 'Describe your vibe — AI structures it for you'),
            html: `<div class="qd-scene">
                <div class="qd-section qd-open"><span class="qd-badge qd-badge-openai">OpenAI</span><span class="qd-section-title">Music Profile</span></div>
                <div class="qd-profile-area">
                    <div class="qd-textarea qd-typing">I love energetic rock with theatrical vocals like Queen. High-energy and melodic!</div>
                </div>
                <div class="qd-cursor" style="top:75px;left:70%"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo2_f4', 'Click "AI Profile Update" — profile trained ✓'),
            html: `<div class="qd-scene">
                <div class="qd-section qd-open"><span class="qd-badge qd-badge-openai">OpenAI</span><span class="qd-section-title">Music Profile</span></div>
                <div class="qd-profile-area">
                    <button class="qd-btn qd-btn-primary qd-pulse">🤖 AI Profile Update</button>
                    <div class="qd-status-line qd-fade-in">✓ Last trained: just now</div>
                </div>
                <div class="qd-result-msg">✅ Profile ready!</div>
            </div>`
        }
    ];
}

function _step3Frames() {
    return [
        {
            caption: i18n('quickstart.demo3_f1', 'Expand "Discover Music" in the Spotify section'),
            html: `<div class="qd-scene">
                <div class="qd-section qd-pulse"><span class="qd-badge qd-badge-spotify">Spotify</span><span class="qd-section-title">Discover Music</span><span class="qd-chevron">▼</span></div>
                <div class="qd-body-placeholder"></div>
                <div class="qd-cursor" style="top:18px;left:50%"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo3_f2', 'Choose a playlist mode and set optional filters'),
            html: `<div class="qd-scene">
                <div class="qd-section qd-open"><span class="qd-badge qd-badge-spotify">Spotify</span><span class="qd-section-title">Discover Music</span></div>
                <div class="qd-gen-area">
                    <div class="qd-field"><span class="qd-label">Mode</span><span class="qd-select qd-pulse">Create new ▾</span></div>
                    <div class="qd-field"><span class="qd-label">Audio Filters</span><span class="qd-filter-tags"><span class="qd-tag">Energy 60–90%</span><span class="qd-tag">Tempo 120–150</span></span></div>
                </div>
                <div class="qd-cursor" style="top:55px;right:30px"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo3_f3', 'Click "Generate & Create Playlist"'),
            html: `<div class="qd-scene">
                <div class="qd-section qd-open"><span class="qd-badge qd-badge-spotify">Spotify</span><span class="qd-section-title">Discover Music</span></div>
                <div class="qd-gen-area">
                    <button class="qd-btn qd-btn-primary qd-btn-wide qd-pulse">▶ Generate &amp; Create Playlist</button>
                    <div class="qd-spinner qd-fade-in">⏳ Generating suggestions…</div>
                </div>
                <div class="qd-cursor" style="top:60px;left:50%"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo3_f4', 'Track cards appear as they\'re found ✓'),
            html: `<div class="qd-scene">
                <div class="qd-section qd-open"><span class="qd-badge qd-badge-spotify">Spotify</span><span class="qd-section-title">Discover Music</span></div>
                <div class="qd-track-list">
                    <div class="qd-track qd-pop"><div class="qd-cover"></div><div class="qd-track-info"><span>Bohemian Rhapsody</span><small>Queen</small></div><span class="qd-track-actions">👍 👎 ✕</span></div>
                    <div class="qd-track qd-pop" style="animation-delay:.15s"><div class="qd-cover"></div><div class="qd-track-info"><span>Don't Stop Me Now</span><small>Queen</small></div><span class="qd-track-actions">👍 👎 ✕</span></div>
                    <div class="qd-track qd-pop" style="animation-delay:.3s"><div class="qd-cover"></div><div class="qd-track-info"><span>Thunder</span><small>Imagine Dragons</small></div><span class="qd-track-actions">👍 👎 ✕</span></div>
                </div>
                <div class="qd-result-msg">✅ 10 tracks added!</div>
            </div>`
        }
    ];
}

function _step4Frames() {
    return [
        {
            caption: i18n('quickstart.demo4_f1', 'Click album art to open the preview overlay'),
            html: `<div class="qd-scene">
                <div class="qd-track-list">
                    <div class="qd-track qd-pulse"><div class="qd-cover qd-cover-clickable">▶</div><div class="qd-track-info"><span>Bohemian Rhapsody</span><small>Queen</small></div><span class="qd-track-actions">👍 👎 ✕</span></div>
                    <div class="qd-track"><div class="qd-cover"></div><div class="qd-track-info"><span>Don't Stop Me Now</span><small>Queen</small></div><span class="qd-track-actions">👍 👎 ✕</span></div>
                </div>
                <div class="qd-cursor" style="top:25px;left:28px"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo4_f2', 'Listen to the ~30 s preview — browse with ‹ / ›'),
            html: `<div class="qd-scene">
                <div class="qd-overlay qd-fade-in">
                    <div class="qd-preview-bar">
                        <span class="qd-nav-arrow">‹</span>
                        <div class="qd-embed"><div class="qd-embed-inner">♫ Spotify Preview<br><small>Bohemian Rhapsody — Queen</small></div></div>
                        <span class="qd-nav-arrow">›</span>
                    </div>
                    <div class="qd-preview-actions"><span class="qd-action-tab">👍</span><span class="qd-action-tab">👎</span><span class="qd-action-tab">✕</span></div>
                </div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo4_f3', 'Like 👍 or Dislike 👎 with an optional reason'),
            html: `<div class="qd-scene">
                <div class="qd-overlay">
                    <div class="qd-preview-bar">
                        <div class="qd-embed"><div class="qd-embed-inner">♫ Bohemian Rhapsody — Queen</div></div>
                    </div>
                    <div class="qd-preview-actions"><span class="qd-action-tab qd-tab-active-like qd-pulse">👍</span><span class="qd-action-tab">👎</span><span class="qd-action-tab">✕</span></div>
                    <div class="qd-feedback-form qd-fade-in"><span class="qd-label">Reason (optional)</span><span class="qd-input qd-typing">Perfect energy!</span><button class="qd-btn qd-btn-sm">Submit</button></div>
                </div>
                <div class="qd-cursor" style="bottom:36px;left:50%"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo4_f4', 'Feedback stored — your profile learns ✓'),
            html: `<div class="qd-scene">
                <div class="qd-track-list">
                    <div class="qd-track qd-liked"><div class="qd-cover"></div><div class="qd-track-info"><span>Bohemian Rhapsody</span><small>Queen</small></div><span class="qd-track-badge">👍 Liked</span></div>
                    <div class="qd-track"><div class="qd-cover"></div><div class="qd-track-info"><span>Don't Stop Me Now</span><small>Queen</small></div><span class="qd-track-actions">👍 👎 ✕</span></div>
                </div>
                <div class="qd-result-msg">✅ Feedback saved!</div>
            </div>`
        }
    ];
}

function _step5Frames() {
    return [
        {
            caption: i18n('quickstart.demo5_f1', 'Expand "Refine Playlist" and select a playlist'),
            html: `<div class="qd-scene">
                <div class="qd-section qd-open"><span class="qd-badge qd-badge-spotify">Spotify</span><span class="qd-section-title">Refine Playlist</span></div>
                <div class="qd-gen-area">
                    <div class="qd-field"><span class="qd-select qd-pulse">My Workout Mix ▾</span></div>
                    <button class="qd-btn qd-btn-outline">🔄 Load Playlist</button>
                </div>
                <div class="qd-cursor" style="top:55px;left:50%"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo5_f2', 'Click "Load Playlist" to see all tracks'),
            html: `<div class="qd-scene">
                <div class="qd-section qd-open"><span class="qd-badge qd-badge-spotify">Spotify</span><span class="qd-section-title">Refine Playlist</span></div>
                <div class="qd-track-list">
                    <div class="qd-track"><div class="qd-cover"></div><div class="qd-track-info"><span>Bohemian Rhapsody</span><small>Queen</small></div><span class="qd-track-actions">👍 👎 ✕</span></div>
                    <div class="qd-track"><div class="qd-cover"></div><div class="qd-track-info"><span>Stairway to Heaven</span><small>Led Zeppelin</small></div><span class="qd-track-actions">👍 👎 ✕</span></div>
                    <div class="qd-track"><div class="qd-cover"></div><div class="qd-track-info"><span>Low-fi beat #47</span><small>Unknown</small></div><span class="qd-track-actions">👍 👎 ✕</span></div>
                </div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo5_f3', 'Like, dislike, or dismiss tracks one by one'),
            html: `<div class="qd-scene">
                <div class="qd-track-list">
                    <div class="qd-track qd-liked"><div class="qd-cover"></div><div class="qd-track-info"><span>Bohemian Rhapsody</span><small>Queen</small></div><span class="qd-track-badge">👍</span></div>
                    <div class="qd-track qd-liked"><div class="qd-cover"></div><div class="qd-track-info"><span>Stairway to Heaven</span><small>Led Zeppelin</small></div><span class="qd-track-badge">👍</span></div>
                    <div class="qd-track qd-disliked qd-pulse"><div class="qd-cover"></div><div class="qd-track-info"><span class="qd-strikethrough">Low-fi beat #47</span><small>Unknown</small></div><span class="qd-track-badge qd-badge-red">👎</span></div>
                </div>
                <div class="qd-cursor" style="top:100px;right:20px"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo5_f4', 'Playlist cleaned up — taste profile refined ✓'),
            html: `<div class="qd-scene">
                <div class="qd-track-list">
                    <div class="qd-track qd-liked"><div class="qd-cover"></div><div class="qd-track-info"><span>Bohemian Rhapsody</span><small>Queen</small></div><span class="qd-track-badge">👍</span></div>
                    <div class="qd-track qd-liked"><div class="qd-cover"></div><div class="qd-track-info"><span>Stairway to Heaven</span><small>Led Zeppelin</small></div><span class="qd-track-badge">👍</span></div>
                </div>
                <div class="qd-result-msg">✅ Playlist refined!</div>
            </div>`
        }
    ];
}

function _step6Frames() {
    return [
        {
            caption: i18n('quickstart.demo6_f1', 'Generate again — each run gets better'),
            html: `<div class="qd-scene">
                <div class="qd-section qd-open"><span class="qd-badge qd-badge-spotify">Spotify</span><span class="qd-section-title">Discover Music</span></div>
                <div class="qd-gen-area">
                    <button class="qd-btn qd-btn-primary qd-btn-wide qd-pulse">▶ Generate &amp; Create Playlist</button>
                    <div class="qd-status-line qd-fade-in">Run #3 — your profile has improved from 12 feedbacks</div>
                </div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo6_f2', 'Use Band/Song Analysis to discover new artists'),
            html: `<div class="qd-scene">
                <div class="qd-section qd-open"><span class="qd-badge qd-badge-openai">OpenAI</span><span class="qd-section-title">Band/Song Analysis</span></div>
                <div class="qd-gen-area">
                    <div class="qd-field"><span class="qd-input">Queen</span></div>
                    <button class="qd-btn qd-btn-outline qd-pulse">Analyse</button>
                    <div class="qd-analysis-result qd-fade-in">
                        <span class="qd-tag">Rock</span><span class="qd-tag">Theatrical</span><span class="qd-tag">High Energy</span>
                        <div style="margin-top:6px"><button class="qd-btn qd-btn-sm">⇒ Use All as Filters</button></div>
                    </div>
                </div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo6_f3', 'Your profile grows stronger with every interaction ✓'),
            html: `<div class="qd-scene qd-scene-center">
                <div class="qd-profile-growth">
                    <div class="qd-growth-bar" style="--pct:30%">Run 1</div>
                    <div class="qd-growth-bar" style="--pct:55%">Run 2</div>
                    <div class="qd-growth-bar" style="--pct:80%">Run 3</div>
                    <div class="qd-growth-bar qd-growth-current" style="--pct:95%">Run 4</div>
                </div>
                <div class="qd-result-msg">🎯 Profile accuracy improves each run!</div>
            </div>`
        }
    ];
}

const DEMOS = [null, _step1Frames, _step2Frames, _step3Frames, _step4Frames, _step5Frames, _step6Frames];

/* ── State management ── */
const _state = new Map();
const AUTO_PLAY_MS = 3500;

function _getFrames(step) {
    const fn = DEMOS[step];
    return fn ? fn() : [];
}

function _ensureState(step) {
    if (!_state.has(step)) {
        _state.set(step, { frame: 0, timer: null, playing: false });
    }
    return _state.get(step);
}

/* ── Public API ── */

export function qsDemoNext(step) {
    const s = _ensureState(step);
    const frames = _getFrames(step);
    if (!frames.length) return;
    s.frame = (s.frame + 1) % frames.length;
    _renderFrame(step);
}

export function qsDemoPrev(step) {
    const s = _ensureState(step);
    const frames = _getFrames(step);
    if (!frames.length) return;
    s.frame = (s.frame - 1 + frames.length) % frames.length;
    _renderFrame(step);
}

export function qsDemoToggle(step) {
    const s = _ensureState(step);
    if (s.playing) {
        clearInterval(s.timer);
        s.timer = null;
        s.playing = false;
    } else {
        s.playing = true;
        qsDemoNext(step);
        s.timer = setInterval(() => qsDemoNext(step), AUTO_PLAY_MS);
    }
    _updatePlayBtn(step);
}

/** Reset a single demo to frame 0 and stop auto-play. */
export function qsDemoReset(step) {
    const s = _ensureState(step);
    if (s.timer) { clearInterval(s.timer); s.timer = null; }
    s.frame = 0;
    s.playing = false;
    _renderFrame(step);
}

/** Initialize all demo players, render first frames, and auto-play. */
export function initAllDemos() {
    for (let i = 1; i <= 6; i++) {
        const s = _ensureState(i);
        _renderFrame(i);
        // Auto-start playback
        if (!s.playing) {
            s.playing = true;
            s.timer = setInterval(() => qsDemoNext(i), AUTO_PLAY_MS);
            _updatePlayBtn(i);
        }
    }
}

/** Stop all auto-play timers. */
export function destroyAllDemos() {
    for (const [, s] of _state) {
        if (s.timer) clearInterval(s.timer);
    }
    _state.clear();
}

/* ── Rendering ── */

function _renderFrame(step) {
    const s = _ensureState(step);
    const frames = _getFrames(step);
    const el = document.querySelector(`.qs-demo-player[data-qs-demo="${step}"]`);
    if (!el || !frames.length) return;

    const frame = frames[s.frame];
    const viewport = el.querySelector('.qs-demo-viewport');
    const caption = el.querySelector('.qs-demo-caption');
    const counter = el.querySelector('.qs-demo-counter');

    if (viewport) {
        viewport.classList.add('qd-transitioning');
        setTimeout(() => {
            viewport.innerHTML = frame.html;
            viewport.classList.remove('qd-transitioning');
        }, 150);
    }
    if (caption) caption.textContent = frame.caption;
    if (counter) counter.textContent = `${s.frame + 1} / ${frames.length}`;
    _updatePlayBtn(step);
}

function _updatePlayBtn(step) {
    const s = _ensureState(step);
    const el = document.querySelector(`.qs-demo-player[data-qs-demo="${step}"] .qs-demo-play`);
    if (el) el.textContent = s.playing ? '⏸' : '▶';
}

