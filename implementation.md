# Implementation Plan — Playlist Review & Naming Rework

## Summary

Add a new **"Refine Playlist"** section that lets users load an existing Spotify playlist, browse its tracks, and give retroactive feedback (like / dislike / dismiss). Rework section naming for clarity and consistency.

---

## Naming Proposal

The current names mix intent ("Creation") with provider ("Spotify Playlist"). With two playlist-related sections, clearer names are needed:

| Current Name | Proposed Name | Rationale |
|---|---|---|
| **Spotify Playlist Creation** | **✨ Discover Music** | Emphasises the AI discovery purpose while remaining action-oriented. |
| *(new section)* | **🔄 Refine Playlist** | "Refine" implies taking something existing and making it better through feedback. |
| **Run History** | **🕓 History** | Shorter, as requested. |

**Button labels:**

| Current | Proposed |
|---|---|
| `Generate & Create Playlist` | `▶ Generate & Create Playlist` *(unchanged — already clear)* |
| *(new)* | `🔄 Load Playlist` |

**Section subtitles:**

| Section | Subtitle |
|---|---|
| Discover Music | *Generate AI-powered playlists and save them to Spotify.* |
| Refine Playlist | *Load an existing playlist and give track-by-track feedback to refine your taste profile.* |
| History | *View past generation runs.* |

> **"Discover"** emphasises the AI/generative nature. **"Refine Playlist"** makes the feedback purpose explicit. Dismiss removes the track from the Spotify playlist without recording profile feedback; dislike records feedback AND removes from playlist.

---

## UI Layout (top → bottom, inside Spotify section)

```
┌─ Spotify Provider Section ──────────────────────────┐
│                                                      │
│  🎧 Discover Music          [Show]                   │
│  ┌──────────────────────────────────────────────┐    │
│  │ Playlist mode / name / picker                │    │
│  │ [▶ Generate & Create Playlist]               │    │
│  └──────────────────────────────────────────────┘    │
│                                                      │
│  ── Discover suggestion list ──────────────────────  │
│  (statusBox, playlistLinkBox, songlistCounter,       │
│   trackList — existing, unchanged)                   │
│                                                      │
│  🔄 Refine Playlist          [Show]                   │
│  ┌──────────────────────────────────────────────┐    │
│  │ [Playlist dropdown ▾]                        │    │
│  │ [🔄 Load Playlist]                            │    │
│  └──────────────────────────────────────────────┘    │
│                                                      │
│  ── Review track list ─────────────────────────────  │
│  (reviewTrackList — new, similar card style)         │
│  Actions: 👍 Like  👎 Dislike  ✕ Dismiss             │
│                                                      │
│  🕓 History                  [Show history]           │
│  ┌──────────────────────────────────────────────┐    │
│  │ expandable run entries (unchanged)           │    │
│  └──────────────────────────────────────────────┘    │
│                                                      │
└──────────────────────────────────────────────────────┘
```

---

## Behaviour Specification

### Load Playlist
1. User selects a playlist from the dropdown (data should be stored in a shared JS variable to avoid redundant `/api/playlists` calls).
2. Clicks **"🔄 Load Playlist"**.
3. Frontend calls `GET /api/playlist/<playlist_id>/tracks`.
4. Backend fetches all tracks via `sp.playlist_items()`, returns enriched track data (artist, track, uri, cover_url, spotify_url, artist_url, album_url, track_id).
5. Tracks render in `reviewTrackList` with the same card style as the Discover suggestion list.

### Track Actions
| Action | Profile effect | Playlist effect | UI effect |
|---|---|---|---|
| **👍 Like** | Records like in profile | *None* — track stays in playlist | Opens form. On submit, card animates out to clear the queue. |
| **👎 Dislike** | Records dislike in profile | Removes track from Spotify playlist | Opens form. On submit, card animates out to clear the queue. |
| **✕ Dismiss (The "X" button)** | *None* | Removes track from Spotify playlist | Calls `/api/remove` to delete from playlist, then card animates out. |

> "Dismiss" (the "X" button on the track card) removes the track from the Spotify playlist without recording any taste profile feedback. "Like" and "Dislike" both animate out after the feedback form is submitted to help the user clear their review queue.

### Preview
Clicking album art opens the same Spotify embed overlay (shared with Discover). The prev/next navigation operates within the *active* track list (review list when opened from review cards, discover list when opened from discover cards).

**Inline Preview Feedback (New UI):**
- The preview container size should be increased by 20%.
- Add action icon buttons next to the preview container: **👍 (Like)**, **👎 (Dislike)**, and **✕ (Dismiss)**.
- Clicking **Like** or **Dislike** expands a feedback form window to the right (Artist, Track, Reason). Switching between Like/Dislike swaps the form state accordingly.
- **Submitting Like**: Records like in profile.
- **Submitting Dislike**: Records dislike in profile + removes track from Spotify playlist.
- **Clicking ✕ (Dismiss)**: Removes track from the Spotify playlist directly (no profile feedback).
- **Auto-advance & Sync**: After any successful action (Submit or Dismiss), the preview must automatically jump to the next track. The track counter in the preview (`X / Y`) and the global track counts in the main UI suggestion/review lists must update instantly to reflect the removed track.

---

## Dropdown Arrow Adjustment

All `<select>` elements globally get `padding-right` increased so the native dropdown arrow sits ~10px further from the right edge. This is a one-line CSS change.

---

## File Changes

### Backend

| File | Change | Complexity |
|---|---|---|
| `core/src/playlist.py` | Add `get_playlist_tracks(playlist_id)` — fetches all tracks with metadata | Small |
| `app.py` | Add `GET /api/playlist/<playlist_id>/tracks` endpoint | Small |
| `app.py` | Import `get_playlist_tracks` | Trivial |

### Frontend — Templates

| File | Change |
|---|---|
| `frontend/templates/base.html` | Insert `{% include "playlist_review.html" %}` between tracklist and history |
| `frontend/templates/playlist_review.html` | **New file** — collapsible section with playlist dropdown + load button |
| `frontend/templates/review_tracklist.html` | **New file** — `<ul id="reviewTrackList">` (empty, JS-rendered) |
| `frontend/templates/generate_section.html` | Rename title to "Discover Music" |
| `frontend/templates/run_history.html` | Rename title to "History" |

### Frontend — JavaScript

| File | Change |
|---|---|
| `frontend/static/js/modules/review.js` | **New file** — `toggleReviewBody()`, `loadPlaylistTracks()`, `renderReviewTracks()`, `dismissReviewTrack()`, review-specific feedback wrappers |
| `frontend/static/js/modules/feedback.js` | Extract shared track-card HTML builder into a helper (used by both `tracklist.js` and `review.js`) to avoid duplication |
| `frontend/static/js/modules/state.js` | Add `reviewTracks` array + `setReviewTracks()` / `spliceReviewTrack()` |
| `frontend/static/js/modules/preview.js` | Accept an optional `source` param (`'discover'` or `'review'`) so prev/next navigates the correct list |
| `frontend/static/js/modules/tracklist.js` | Use shared track-card builder from feedback.js |
| `frontend/static/js/main.js` | Import + expose new review functions as `window.*` globals |

### Frontend — CSS

| File | Change |
|---|---|
| `frontend/static/css/styles.css` | Dropdown arrow padding tweak (global `select` rule) |
| `frontend/static/css/styles.css` | Review section styling (reuses existing `.track-item` / `.track-list` classes — minimal new CSS) |

### i18n

| File | Change |
|---|---|
| `frontend/static/i18n/en.json` | Add `review.*` keys, rename `generate.title` → "Discover Music", `history.title` → "History" |
| `frontend/static/i18n/de.json` | Same, German translations |

### Tests

| File | Change |
|---|---|
| `core/tests/test_playlist.py` | Add tests for `get_playlist_tracks()` |
| `core/tests/test_app.py` | Add tests for `GET /api/playlist/<id>/tracks` |
| `core/tests/test_app.py` | Update any assertions referencing old section names |

### Documentation

| File | Change |
|---|---|
| `README.md` | Add Refine Playlist feature, update section names |
| `documentation/UserManual.md` | Add Refine Playlist section, update names |
| `documentation/help.md` | Add Refine Playlist section, update names |
| `documentation/TechnicalManual.md` | Add endpoint, update architecture diagram, update names |

---

## Implementation Order

Work will be split across **sub-agents** after approval:

| Step | Sub-agent | Scope |
|---|---|---|
| 0 | **Bug Fixes & UI Tweaks** | 1. Investigate and fix the Run History track display bug where tracks show as "a — b".<br>2. Fix the issue where clicking the Play button on the Album cover does not autoplay the Spotify preview.<br>3. Update the Spotify preview container color scheme to visually meld with the embedded player, and modify the arrow buttons to stand out against the new background. |
| 1 | **Backend** | `get_playlist_tracks()` in `playlist.py` + endpoint in `app.py` + tests |
| 2 | **Frontend Core** | New template files, `review.js` module, state additions, `main.js` wiring |
| 3 | **Shared Track Card** | Extract card HTML builder, update `tracklist.js` and `review.js` to use it |
| 4 | **Preview & Inline Feedback** | Update `preview.js` to support source-switching between lists. Increase preview container size by 20%. Add Like/Dislike/Dismiss action buttons next to the player with a sliding feedback form to the right. Wire up actions to auto-advance to next song and update local/global counters. |
| 5 | **Rename & CSS** | Section renames in templates + i18n, dropdown arrow CSS fix |
| 6 | **Documentation** | Update all 4 doc files |
| 7 | **Final Test Run** | Run full test suite, verify everything passes |

---

## Agent Directives (No User Input Required)

The following decisions have been finalised for the implementation:
1. **Section naming**: Will be "✨ Discover Music" and "🔄 Refine Playlist".
2. **Dismiss behaviour**: Removes the track from the Spotify playlist (via `/api/remove`) but records no profile feedback. Then animates the card out.
3. **Like behaviour in review**: The card will animate out *after* the feedback form is successfully submitted.
4. **Playlist dropdown caching**: Implement a simple shared cache in `state.js` or `playlist-mode.js` to ensure `/api/playlists` is only fetched once and used by both the Discover and Refine dropdowns.
