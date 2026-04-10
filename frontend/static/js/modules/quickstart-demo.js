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
                <div class="qd-header">
                    <span class="qd-logo">SpotyVibe</span>
                    <div class="qd-lang-toggle"><span class="qd-lang-active">EN</span><span>DE</span></div>
                    <div class="qd-burger qd-pulse"><div class="qd-burger-line"></div><div class="qd-burger-line"></div><div class="qd-burger-line"></div></div>
                </div>
                <div class="qd-tab-bar">
                    <div class="qd-tab qd-tab-active">AI Profile &amp; Analysis</div>
                    <div class="qd-tab">Discover &amp; Playlists</div>
                    <div class="qd-tab">Run History</div>
                </div>
                <div class="qd-provider qd-provider-openai" style="opacity:0.4">
                    <div class="qd-provider-header"><div class="qd-provider-name">OpenAI</div><div class="qd-pills-row"><span class="qd-pill qd-pill-err">Key missing</span></div></div>
                </div>
                <div class="qd-cursor" style="top:10px;right:16px"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo1_f2', 'Select "🔑 Credentials" from the dropdown'),
            html: `<div class="qd-scene">
                <div class="qd-header">
                    <span class="qd-logo">SpotyVibe</span>
                    <div class="qd-lang-toggle"><span class="qd-lang-active">EN</span><span>DE</span></div>
                    <div class="qd-burger qd-active"><div class="qd-burger-line"></div><div class="qd-burger-line"></div><div class="qd-burger-line"></div></div>
                </div>
                <div class="qd-dropdown">
                    <div class="qd-menu-item qd-highlight qd-pulse">🔑 Credentials</div>
                    <div class="qd-menu-item">⚙️ Settings</div>
                    <div class="qd-menu-item">🔌 Connect Spotify</div>
                    <div class="qd-menu-item">❓ Help</div>
                </div>
                <div class="qd-cursor" style="top:48px;right:36px"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo1_f3', 'Enter your API keys and click Save'),
            html: `<div class="qd-scene">
                <div class="qd-mini-modal">
                    <div class="qd-modal-title">🔑 Credentials</div>
                    <div class="qd-field"><span class="qd-label">OpenAI API Key</span><span class="qd-input qd-typing">sk-proj-abc…xyz</span></div>
                    <div class="qd-field"><span class="qd-label">Spotify Client ID</span><span class="qd-input qd-typing">a1b2c3d4e5…</span></div>
                    <div class="qd-field"><span class="qd-label">Spotify Client Secret</span><span class="qd-input qd-typing">x9y8z7w6…</span></div>
                    <div style="display:flex;gap:6px;justify-content:flex-end;padding-top:4px">
                        <button class="qd-btn qd-btn-secondary">Cancel</button>
                        <button class="qd-btn qd-btn-primary qd-pulse">Save</button>
                    </div>
                </div>
                <div class="qd-cursor" style="bottom:20px;right:30px"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo1_f4', 'Connect Spotify — status pills turn green ✓'),
            html: `<div class="qd-scene">
                <div class="qd-header">
                    <span class="qd-logo">SpotyVibe</span>
                    <div class="qd-lang-toggle"><span class="qd-lang-active">EN</span><span>DE</span></div>
                    <div class="qd-burger"><div class="qd-burger-line"></div><div class="qd-burger-line"></div><div class="qd-burger-line"></div></div>
                </div>
                <div class="qd-tab-bar">
                    <div class="qd-tab qd-tab-active">AI Profile &amp; Analysis</div>
                    <div class="qd-tab">Discover &amp; Playlists</div>
                    <div class="qd-tab">Run History</div>
                </div>
                <div class="qd-provider qd-provider-openai">
                    <div class="qd-provider-header">
                        <div class="qd-provider-name">OpenAI</div>
                        <div class="qd-pills-row">
                            <span class="qd-pill qd-pill-green qd-pop">Key configured</span>
                            <span class="qd-pill qd-pill-green qd-pop" style="animation-delay:.15s">gpt-5.4</span>
                        </div>
                    </div>
                </div>
                <div class="qd-result-msg qd-fade-in">✅ Ready to go!</div>
            </div>`
        }
    ];
}

function _step2Frames() {
    return [
        {
            caption: i18n('quickstart.demo2_f1', 'Expand the Music Profile section'),
            html: `<div class="qd-scene">
                <div class="qd-provider qd-provider-openai">
                    <div class="qd-provider-header"><div class="qd-provider-name">OpenAI</div><div class="qd-pills-row"><span class="qd-pill qd-pill-green">Key configured</span></div></div>
                    <div class="qd-accordion qd-pulse">
                        <div class="qd-accordion-header">
                            <h4><span class="qd-icon">🎯</span> Music Profile</h4>
                            <span class="qd-accordion-toggle">Show</span>
                        </div>
                    </div>
                    <div class="qd-accordion" style="opacity:0.4">
                        <div class="qd-accordion-header"><h4><span class="qd-icon">🔍</span> Band/Song Analysis</h4><span class="qd-accordion-toggle">Show</span></div>
                    </div>
                </div>
                <div class="qd-cursor" style="top:52px;left:50%"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo2_f2', 'Create a new profile and give it a name'),
            html: `<div class="qd-scene">
                <div class="qd-provider qd-provider-openai">
                    <div class="qd-accordion qd-open">
                        <div class="qd-accordion-header"><h4><span class="qd-icon">🎯</span> Music Profile</h4><span class="qd-accordion-toggle">Hide</span></div>
                        <div class="qd-accordion-body">
                            <div class="qd-accordion" style="border-color:rgba(255,255,255,0.1)">
                                <div class="qd-accordion-header"><h4><span class="qd-icon">👤</span> Profiles</h4></div>
                                <div class="qd-accordion-body">
                                    <div class="qd-select" style="margin-bottom:4px">🎸 Emma ▾</div>
                                    <button class="qd-btn qd-btn-primary qd-pulse" style="width:100%">+ Create new Profile</button>
                                    <div class="qd-field qd-fade-in" style="flex-direction:row;gap:6px"><span class="qd-input qd-typing" style="flex:1">My Workout Mix</span><span style="color:var(--primary);font-size:0.7rem">✓</span></div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="qd-cursor" style="top:108px;left:50%"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo2_f3', 'Describe your vibe — AI structures it for you'),
            html: `<div class="qd-scene">
                <div class="qd-provider qd-provider-openai">
                    <div class="qd-accordion qd-open">
                        <div class="qd-accordion-header"><h4><span class="qd-icon">🎯</span> Music Profile</h4><span class="qd-accordion-toggle">Hide</span></div>
                        <div class="qd-accordion-body">
                            <div class="qd-accordion" style="border-color:rgba(255,255,255,0.1);opacity:0.4"><div class="qd-accordion-header"><h4><span class="qd-icon">👤</span> Profiles</h4></div></div>
                            <div class="qd-accordion qd-open qd-pulse">
                                <div class="qd-accordion-header"><h4><span class="qd-icon">💬</span> Describe Your Vibe</h4></div>
                                <div class="qd-accordion-body">
                                    <div class="qd-textarea qd-typing">I love energetic rock with theatrical vocals like Queen. High-energy and melodic!</div>
                                </div>
                            </div>
                            <div class="qd-accordion" style="opacity:0.4"><div class="qd-accordion-header"><h4><span class="qd-icon">🎵</span> Core Description</h4></div></div>
                        </div>
                    </div>
                </div>
                <div class="qd-cursor" style="top:115px;left:60%"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo2_f4', 'Click "AI Profile Update" — profile trained ✓'),
            html: `<div class="qd-scene">
                <div class="qd-provider qd-provider-openai">
                    <div class="qd-accordion qd-open">
                        <div class="qd-accordion-header">
                            <h4><span class="qd-icon">🎯</span> Music Profile</h4>
                            <span class="qd-status-line qd-fade-in">✓ Last trained: just now</span>
                        </div>
                        <div class="qd-accordion-body">
                            <div style="display:flex;gap:6px">
                                <button class="qd-btn qd-btn-primary qd-pulse" style="flex:1">🤖 AI Profile Update</button>
                                <button class="qd-btn qd-btn-secondary" style="flex:1">💾 Save without AI</button>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="qd-result-msg qd-fade-in">✅ Profile trained!</div>
            </div>`
        }
    ];
}

function _step3Frames() {
    return [
        {
            caption: i18n('quickstart.demo3_f1', 'Expand "Discover Music" in the Spotify section'),
            html: `<div class="qd-scene">
                <div class="qd-provider qd-provider-spotify">
                    <div class="qd-provider-header"><div class="qd-provider-name">Spotify</div><div class="qd-pills-row"><span class="qd-pill qd-pill-green">Connected</span></div></div>
                    <div class="qd-accordion qd-pulse">
                        <div class="qd-accordion-header">
                            <h4><span class="qd-icon">🎧</span> Discover Music</h4>
                            <span class="qd-accordion-toggle">Show</span>
                        </div>
                    </div>
                    <div class="qd-accordion" style="opacity:0.4"><div class="qd-accordion-header"><h4><span class="qd-icon">🔄</span> Refine Playlist</h4><span class="qd-accordion-toggle">Show</span></div></div>
                </div>
                <div class="qd-cursor" style="top:48px;left:50%"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo3_f2', 'Choose a playlist mode and set optional filters'),
            html: `<div class="qd-scene">
                <div class="qd-provider qd-provider-spotify">
                    <div class="qd-accordion qd-open">
                        <div class="qd-accordion-header"><h4><span class="qd-icon">🎧</span> Discover Music</h4><span class="qd-accordion-toggle">Hide</span></div>
                        <div class="qd-accordion-body">
                            <div class="qd-radio-group">
                                <div class="qd-radio"><div class="qd-radio-dot"></div> Default</div>
                                <div class="qd-radio qd-active qd-pulse"><div class="qd-radio-dot"></div> Create new</div>
                                <div class="qd-radio"><div class="qd-radio-dot"></div> Append</div>
                                <div class="qd-radio"><div class="qd-radio-dot"></div> Replace</div>
                            </div>
                            <div class="qd-field"><span class="qd-input qd-typing" style="font-family:inherit">SpotyVibe {date}</span></div>
                            <div class="qd-accordion" style="border-color:rgba(30,215,96,0.12)">
                                <div class="qd-accordion-header"><h4 style="font-size:0.65rem">🎚 Audio Filters (optional)</h4></div>
                                <div class="qd-accordion-body">
                                    <div class="qd-filter-tags"><span class="qd-tag">Energy 60–90%</span><span class="qd-tag">Tempo 120–150</span><span class="qd-tag">Valence 50–80%</span></div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="qd-cursor" style="top:50px;left:55%"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo3_f3', 'Click "Generate & Create Playlist"'),
            html: `<div class="qd-scene">
                <div class="qd-provider qd-provider-spotify">
                    <div class="qd-accordion qd-open">
                        <div class="qd-accordion-header"><h4><span class="qd-icon">🎧</span> Discover Music</h4></div>
                        <div class="qd-accordion-body">
                            <button class="qd-btn qd-btn-primary qd-btn-wide qd-pulse">▶ Generate &amp; Create Playlist</button>
                            <div class="qd-spinner qd-fade-in">Generating suggestions…</div>
                        </div>
                    </div>
                </div>
                <div class="qd-cursor" style="top:60px;left:50%"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo3_f4', 'Track cards appear as they\'re found ✓'),
            html: `<div class="qd-scene">
                <div class="qd-provider qd-provider-spotify">
                    <div class="qd-accordion qd-open">
                        <div class="qd-accordion-header"><h4><span class="qd-icon">🎧</span> Discover Music</h4></div>
                        <div class="qd-accordion-body" style="gap:4px">
                            <div class="qd-track-list">
                                <div class="qd-track qd-pop"><div class="qd-cover"></div><div class="qd-track-info"><span>Bohemian Rhapsody</span><small>Queen</small></div><div class="qd-track-actions"><span class="qd-action-btn">👍</span><span class="qd-action-btn">👎</span><span class="qd-action-btn">✕</span></div></div>
                                <div class="qd-track qd-pop" style="animation-delay:.15s"><div class="qd-cover"></div><div class="qd-track-info"><span>Don't Stop Me Now</span><small>Queen</small></div><div class="qd-track-actions"><span class="qd-action-btn">👍</span><span class="qd-action-btn">👎</span><span class="qd-action-btn">✕</span></div></div>
                                <div class="qd-track qd-pop" style="animation-delay:.3s"><div class="qd-cover"></div><div class="qd-track-info"><span>Thunder</span><small>Imagine Dragons</small></div><div class="qd-track-actions"><span class="qd-action-btn">👍</span><span class="qd-action-btn">👎</span><span class="qd-action-btn">✕</span></div></div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="qd-result-msg qd-fade-in">✅ 10 tracks added to Spotify!</div>
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
                    <div class="qd-track qd-pulse">
                        <div class="qd-cover qd-cover-clickable"></div>
                        <div class="qd-track-info"><span>Bohemian Rhapsody</span><small>Queen</small></div>
                        <div class="qd-spotify-links"><span>🎵</span><span>🎤</span><span>💿</span></div>
                        <div class="qd-track-actions"><span class="qd-action-btn">👍</span><span class="qd-action-btn">👎</span><span class="qd-action-btn">✕</span></div>
                    </div>
                    <div class="qd-track">
                        <div class="qd-cover"></div>
                        <div class="qd-track-info"><span>Don't Stop Me Now</span><small>Queen</small></div>
                        <div class="qd-spotify-links"><span>🎵</span><span>🎤</span><span>💿</span></div>
                        <div class="qd-track-actions"><span class="qd-action-btn">👍</span><span class="qd-action-btn">👎</span><span class="qd-action-btn">✕</span></div>
                    </div>
                    <div class="qd-track" style="opacity:0.6">
                        <div class="qd-cover"></div>
                        <div class="qd-track-info"><span>Thunder</span><small>Imagine Dragons</small></div>
                        <div class="qd-spotify-links"><span>🎵</span><span>🎤</span><span>💿</span></div>
                        <div class="qd-track-actions"><span class="qd-action-btn">👍</span><span class="qd-action-btn">👎</span><span class="qd-action-btn">✕</span></div>
                    </div>
                </div>
                <div class="qd-cursor" style="top:18px;left:24px"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo4_f2', 'Listen to the ~30 s preview — browse with ‹ / ›'),
            html: `<div class="qd-scene">
                <div class="qd-overlay qd-fade-in">
                    <div class="qd-preview-bar">
                        <span class="qd-nav-arrow">‹</span>
                        <div class="qd-embed"><div class="qd-embed-inner">♫ Spotify Preview<small>Bohemian Rhapsody — Queen</small></div></div>
                        <span class="qd-nav-arrow">›</span>
                    </div>
                    <div style="text-align:center;font-size:0.55rem;color:var(--text-muted)">1 / 10</div>
                    <div class="qd-preview-actions"><span class="qd-action-tab">👍</span><span class="qd-action-tab">👎</span><span class="qd-action-tab">✕</span></div>
                </div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo4_f3', 'Like 👍 or Dislike 👎 with an optional reason'),
            html: `<div class="qd-scene">
                <div class="qd-overlay">
                    <div class="qd-preview-bar">
                        <div class="qd-embed"><div class="qd-embed-inner">♫ Bohemian Rhapsody<small>Queen</small></div></div>
                    </div>
                    <div class="qd-preview-actions"><span class="qd-action-tab qd-tab-active-like qd-pulse">👍</span><span class="qd-action-tab">👎</span><span class="qd-action-tab">✕</span></div>
                    <div class="qd-feedback-form qd-fade-in">
                        <div style="display:flex;flex-direction:column;gap:3px;flex:1">
                            <span class="qd-label">Reason (optional)</span>
                            <span class="qd-input qd-typing" style="font-family:inherit">Perfect energy!</span>
                        </div>
                        <button class="qd-btn qd-btn-primary qd-btn-sm">Submit</button>
                    </div>
                </div>
                <div class="qd-cursor" style="bottom:22px;right:24px"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo4_f4', 'Feedback stored — your profile learns ✓'),
            html: `<div class="qd-scene">
                <div class="qd-track-list">
                    <div class="qd-track qd-liked">
                        <div class="qd-cover"></div>
                        <div class="qd-track-info"><span>Bohemian Rhapsody</span><small>Queen</small></div>
                        <span class="qd-track-badge">👍 Liked</span>
                    </div>
                    <div class="qd-track">
                        <div class="qd-cover"></div>
                        <div class="qd-track-info"><span>Don't Stop Me Now</span><small>Queen</small></div>
                        <div class="qd-track-actions"><span class="qd-action-btn">👍</span><span class="qd-action-btn">👎</span><span class="qd-action-btn">✕</span></div>
                    </div>
                </div>
                <div class="qd-result-msg qd-fade-in">✅ Feedback saved — profile updated!</div>
            </div>`
        }
    ];
}

function _step5Frames() {
    return [
        {
            caption: i18n('quickstart.demo5_f1', 'Expand "Refine Playlist" and select a playlist'),
            html: `<div class="qd-scene">
                <div class="qd-provider qd-provider-spotify">
                    <div class="qd-accordion qd-open">
                        <div class="qd-accordion-header"><h4><span class="qd-icon">🔄</span> Refine Playlist</h4><span class="qd-accordion-toggle">Hide</span></div>
                        <div class="qd-accordion-body">
                            <div class="qd-field" style="flex-direction:row;gap:6px;align-items:center">
                                <div class="qd-select qd-pulse" style="flex:1">My Workout Mix ▾</div>
                                <span style="font-size:0.7rem;color:var(--text-muted)">↻</span>
                            </div>
                            <button class="qd-btn qd-btn-primary" style="width:100%">🔄 Load Playlist</button>
                        </div>
                    </div>
                </div>
                <div class="qd-cursor" style="top:62px;left:50%"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo5_f2', 'Click "Load Playlist" to see all tracks'),
            html: `<div class="qd-scene">
                <div class="qd-provider qd-provider-spotify">
                    <div class="qd-accordion qd-open">
                        <div class="qd-accordion-header"><h4><span class="qd-icon">🔄</span> Refine Playlist</h4></div>
                        <div class="qd-accordion-body" style="gap:4px">
                            <div class="qd-track-list">
                                <div class="qd-track"><div class="qd-cover"></div><div class="qd-track-info"><span>Bohemian Rhapsody</span><small>Queen</small></div><div class="qd-track-actions"><span class="qd-action-btn">👍</span><span class="qd-action-btn">👎</span><span class="qd-action-btn">✕</span></div></div>
                                <div class="qd-track"><div class="qd-cover"></div><div class="qd-track-info"><span>Stairway to Heaven</span><small>Led Zeppelin</small></div><div class="qd-track-actions"><span class="qd-action-btn">👍</span><span class="qd-action-btn">👎</span><span class="qd-action-btn">✕</span></div></div>
                                <div class="qd-track"><div class="qd-cover"></div><div class="qd-track-info"><span>Low-fi beat #47</span><small>Unknown</small></div><div class="qd-track-actions"><span class="qd-action-btn">👍</span><span class="qd-action-btn">👎</span><span class="qd-action-btn">✕</span></div></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo5_f3', 'Like, dislike, or dismiss tracks one by one'),
            html: `<div class="qd-scene">
                <div class="qd-track-list">
                    <div class="qd-track qd-liked">
                        <div class="qd-cover"></div>
                        <div class="qd-track-info"><span>Bohemian Rhapsody</span><small>Queen</small></div>
                        <span class="qd-track-badge">👍 Liked</span>
                    </div>
                    <div class="qd-track qd-liked">
                        <div class="qd-cover"></div>
                        <div class="qd-track-info"><span>Stairway to Heaven</span><small>Led Zeppelin</small></div>
                        <span class="qd-track-badge">👍 Liked</span>
                    </div>
                    <div class="qd-track qd-disliked qd-pulse">
                        <div class="qd-cover"></div>
                        <div class="qd-track-info"><span class="qd-strikethrough">Low-fi beat #47</span><small>Unknown</small></div>
                        <span class="qd-track-badge qd-badge-red">👎 Removed</span>
                    </div>
                </div>
                <div class="qd-cursor" style="top:95px;right:16px"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo5_f4', 'Playlist cleaned up — taste profile refined ✓'),
            html: `<div class="qd-scene">
                <div class="qd-track-list">
                    <div class="qd-track qd-liked">
                        <div class="qd-cover"></div>
                        <div class="qd-track-info"><span>Bohemian Rhapsody</span><small>Queen</small></div>
                        <span class="qd-track-badge">👍</span>
                    </div>
                    <div class="qd-track qd-liked">
                        <div class="qd-cover"></div>
                        <div class="qd-track-info"><span>Stairway to Heaven</span><small>Led Zeppelin</small></div>
                        <span class="qd-track-badge">👍</span>
                    </div>
                </div>
                <div class="qd-result-msg qd-fade-in">✅ Playlist refined — 1 track removed!</div>
            </div>`
        }
    ];
}

function _step6Frames() {
    return [
        {
            caption: i18n('quickstart.demo6_f1', 'Generate again — each run gets better'),
            html: `<div class="qd-scene">
                <div class="qd-provider qd-provider-spotify">
                    <div class="qd-accordion qd-open">
                        <div class="qd-accordion-header"><h4><span class="qd-icon">🎧</span> Discover Music</h4></div>
                        <div class="qd-accordion-body">
                            <button class="qd-btn qd-btn-primary qd-btn-wide qd-pulse">▶ Generate &amp; Create Playlist</button>
                            <div class="qd-status-line qd-fade-in">Run #3 — profile improved from 12 feedbacks</div>
                        </div>
                    </div>
                </div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo6_f2', 'Use Band/Song Analysis to discover new artists'),
            html: `<div class="qd-scene">
                <div class="qd-provider qd-provider-openai">
                    <div class="qd-accordion qd-open">
                        <div class="qd-accordion-header"><h4><span class="qd-icon">🔍</span> Band/Song Analysis</h4></div>
                        <div class="qd-accordion-body">
                            <div class="qd-field" style="flex-direction:row;gap:6px;align-items:center">
                                <span class="qd-input" style="flex:1;font-family:inherit">Queen</span>
                                <button class="qd-btn qd-btn-primary qd-pulse">Analyse</button>
                            </div>
                            <div class="qd-analysis-result qd-fade-in">
                                <span class="qd-tag">Rock</span><span class="qd-tag">Theatrical</span><span class="qd-tag">High Energy</span><span class="qd-tag">Melodic</span>
                                <div style="margin-top:4px;width:100%"><button class="qd-btn qd-btn-sm qd-btn-outline">⇒ Use All as Filters</button></div>
                            </div>
                        </div>
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

function _step7Frames() {
    return [
        {
            caption: i18n('quickstart.demo7_f1', 'Open Band/Song Analysis and enter an artist'),
            html: `<div class="qd-scene">
                <div class="qd-provider qd-provider-openai">
                    <div class="qd-accordion qd-open">
                        <div class="qd-accordion-header"><h4><span class="qd-icon">🔍</span> Band/Song Analysis</h4></div>
                        <div class="qd-accordion-body">
                            <div class="qd-field" style="flex-direction:row;gap:6px;align-items:center">
                                <span class="qd-input qd-typing" style="flex:1;font-family:inherit">Radiohead</span>
                                <span class="qd-input" style="flex:1;font-family:inherit;opacity:0.4">Track (optional)</span>
                            </div>
                            <button class="qd-btn qd-btn-primary qd-pulse" style="margin-top:6px">Analyse</button>
                        </div>
                    </div>
                </div>
                <div class="qd-cursor" style="bottom:30px;right:60px"></div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo7_f2', 'AI generates a detailed breakdown with tags'),
            html: `<div class="qd-scene">
                <div class="qd-provider qd-provider-openai">
                    <div class="qd-accordion qd-open">
                        <div class="qd-accordion-header"><h4><span class="qd-icon">🔍</span> Band/Song Analysis</h4></div>
                        <div class="qd-accordion-body">
                            <div class="qd-analysis-result qd-fade-in">
                                <span class="qd-tag">Alt-Rock</span><span class="qd-tag">Experimental</span><span class="qd-tag">Melancholic</span><span class="qd-tag">Atmospheric</span>
                            </div>
                            <div class="qd-suggestion-box qd-fade-in" style="margin-top:6px">
                                <div style="font-size:0.7rem;font-weight:600;margin-bottom:3px">Profile Suggestions</div>
                                <div style="font-size:0.65rem;opacity:0.8">Core: atmospheric alt-rock with emotional depth…</div>
                                <button class="qd-btn qd-btn-sm qd-btn-outline qd-pulse" style="margin-top:4px">📋 Copy to Profile</button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>`
        },
        {
            caption: i18n('quickstart.demo7_f3', 'Copy suggestions to profile or auto-fill audio filters ✓'),
            html: `<div class="qd-scene">
                <div class="qd-provider qd-provider-openai">
                    <div class="qd-accordion qd-open">
                        <div class="qd-accordion-header"><h4><span class="qd-icon">🔍</span> Band/Song Analysis</h4></div>
                        <div class="qd-accordion-body">
                            <div class="qd-analysis-result">
                                <span class="qd-tag">Alt-Rock</span><span class="qd-tag">Experimental</span><span class="qd-tag">Melancholic</span><span class="qd-tag">Atmospheric</span>
                            </div>
                            <div style="display:flex;gap:6px;margin-top:6px;flex-wrap:wrap">
                                <button class="qd-btn qd-btn-sm qd-btn-outline">📋 Copy to Profile</button>
                                <button class="qd-btn qd-btn-sm qd-btn-outline qd-pulse">🎛️ Use as Filters</button>
                            </div>
                            <div class="qd-result-msg qd-fade-in" style="margin-top:6px">✅ Suggestions copied — profile updated!</div>
                        </div>
                    </div>
                </div>
            </div>`
        }
    ];
}

const DEMOS = [null, _step1Frames, _step2Frames, _step3Frames, _step4Frames, _step5Frames, _step6Frames, _step7Frames];

/* ── State management ── */
const _state = new Map();
const AUTO_PLAY_MS = 3500;
const QS_DEMO_SCALE = 0.72;   // inline player scale-down factor
const QS_LB_SCALE = 1.25;     // lightbox scale-up factor
let _lightboxStep = null;      // step currently shown in lightbox (null = closed)
let _lbMaxHeight = 0;          // cached max frame height for lightbox viewport

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
    // ── Measure the tallest frame across ALL steps.
    //    Hidden pages (display:none) report scrollHeight 0, so we use an
    //    off-screen probe element with the same width as the real viewport.
    const refVp = document.querySelector('.qs-demo-viewport');
    if (!refVp) return;

    const probe = document.createElement('div');
    probe.className = 'qs-demo-viewport';
    Object.assign(probe.style, {
        position: 'fixed', top: '-9999px', left: '-9999px',
        width: refVp.offsetWidth ? refVp.offsetWidth + 'px' : '100%',
        visibility: 'hidden', height: 'auto', overflow: 'visible'
    });
    document.body.appendChild(probe);

    let maxH = 0;
    for (let i = 1; i < DEMOS.length; i++) {
        const frames = _getFrames(i);
        for (const f of frames) {
            probe.innerHTML = f.html;
            if (probe.scrollHeight > maxH) maxH = probe.scrollHeight;
        }
    }
    document.body.removeChild(probe);

    // Apply uniform *scaled* height to every viewport
    if (maxH > 0) {
        const scaledH = Math.ceil(maxH * QS_DEMO_SCALE);
        document.querySelectorAll('.qs-demo-viewport').forEach(vp => {
            vp.style.height = scaledH + 'px';
        });
    }

    // Render first frame & start auto-play
    for (let i = 1; i < DEMOS.length; i++) {
        const s = _ensureState(i);
        _renderFrame(i);
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
    _closeLightbox();
}

/* ── Lightbox (expanded demo view) ── */

/** Open the demo lightbox for the given step at the current frame. */
export function qsDemoExpand(step) {
    _lightboxStep = step;
    // Pause inline auto-play while lightbox is open
    const s = _ensureState(step);
    if (s.playing) {
        clearInterval(s.timer); s.timer = null; s.playing = false;
        _updatePlayBtn(step);
    }
    // Measure tallest frame across ALL steps for uniform lightbox height
    _lbMaxHeight = _measureLightboxMaxHeight();
    _renderLightbox();
}

function _closeLightbox() {
    const lb = document.querySelector('.qs-demo-lightbox');
    if (lb) {
        if (lb._onKey) document.removeEventListener('keydown', lb._onKey);
        lb.remove();
    }
    _lightboxStep = null;
}

function _lbPrev() {
    if (_lightboxStep == null) return;
    qsDemoPrev(_lightboxStep);
}
function _lbNext() {
    if (_lightboxStep == null) return;
    qsDemoNext(_lightboxStep);
}
function _lbToggle() {
    if (_lightboxStep == null) return;
    qsDemoToggle(_lightboxStep);
}

/** Measure the tallest frame across all steps at lightbox scale. */
function _measureLightboxMaxHeight() {
    const probe = document.createElement('div');
    probe.className = 'qs-demo-lightbox-viewport';
    Object.assign(probe.style, {
        position: 'fixed', top: '-9999px', left: '-9999px',
        width: '860px',   // approx inner width of 900px card minus padding
        visibility: 'hidden', height: 'auto', overflow: 'visible'
    });
    document.body.appendChild(probe);

    let maxH = 0;
    for (let i = 1; i < DEMOS.length; i++) {
        const frames = _getFrames(i);
        for (const f of frames) {
            probe.innerHTML = f.html;
            const h = probe.scrollHeight;
            if (h > maxH) maxH = h;
        }
    }
    document.body.removeChild(probe);
    // Apply lightbox scale factor
    return Math.ceil(maxH * QS_LB_SCALE);
}

function _renderLightbox() {
    const step = _lightboxStep;
    if (step == null) return;
    const s = _ensureState(step);
    const frames = _getFrames(step);
    if (!frames.length) return;
    const frame = frames[s.frame];

    let lb = document.querySelector('.qs-demo-lightbox');
    if (!lb) {
        lb = document.createElement('div');
        lb.className = 'qs-demo-lightbox';
        lb.addEventListener('click', e => { if (e.target === lb) _closeLightbox(); });
        lb.innerHTML = `
            <div class="qs-demo-lightbox-card">
                <button class="qs-demo-lightbox-close" aria-label="Close">✕</button>
                <div class="qs-demo-lightbox-viewport"></div>
                <p class="qs-demo-lightbox-caption"></p>
                <div class="qs-demo-lightbox-controls">
                    <button class="qs-demo-btn qs-lb-prev" aria-label="Previous frame">‹</button>
                    <span class="qs-demo-lightbox-counter"></span>
                    <button class="qs-demo-btn qs-lb-next" aria-label="Next frame">›</button>
                    <button class="qs-demo-btn qs-lb-play" aria-label="Play / Pause">▶</button>
                </div>
            </div>`;
        lb.querySelector('.qs-demo-lightbox-close').onclick = _closeLightbox;
        lb.querySelector('.qs-lb-prev').onclick = _lbPrev;
        lb.querySelector('.qs-lb-next').onclick = _lbNext;
        lb.querySelector('.qs-lb-play').onclick = _lbToggle;
        lb._onKey = e => { if (e.key === 'Escape') _closeLightbox(); };
        document.addEventListener('keydown', lb._onKey);
        document.body.appendChild(lb);
    }

    const vp = lb.querySelector('.qs-demo-lightbox-viewport');
    const cap = lb.querySelector('.qs-demo-lightbox-caption');
    const ctr = lb.querySelector('.qs-demo-lightbox-counter');
    const playBtn = lb.querySelector('.qs-lb-play');

    if (vp) {
        vp.innerHTML = frame.html;
        if (_lbMaxHeight > 0) vp.style.height = _lbMaxHeight + 'px';
    }
    if (cap) cap.textContent = frame.caption;
    if (ctr) ctr.textContent = `${s.frame + 1} / ${frames.length}`;
    if (playBtn) playBtn.textContent = s.playing ? '⏸' : '▶';
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

    // Keep lightbox in sync if it's showing this step
    if (_lightboxStep === step) _renderLightbox();
}

function _updatePlayBtn(step) {
    const s = _ensureState(step);
    const el = document.querySelector(`.qs-demo-player[data-qs-demo="${step}"] .qs-demo-play`);
    if (el) el.textContent = s.playing ? '⏸' : '▶';
}

