# Spotify Web API — Developer Reference

This document summarises the Spotify Web API endpoints and patterns used by SpotyVibe, including breaking changes introduced in **February 2026**. Consult the [official Spotify Web API Reference](https://developer.spotify.com/documentation/web-api) before making API changes.

---

## February 2026 Breaking Changes

### Playlist endpoint renamed: `/tracks` → `/items`

| Old (removed) | New (current) |
|---|---|
| `GET /playlists/{id}/tracks` | `GET /playlists/{id}/items` |
| `POST /playlists/{id}/tracks` | `POST /playlists/{id}/items` |
| `PUT /playlists/{id}/tracks` | `PUT /playlists/{id}/items` |
| `DELETE /playlists/{id}/tracks` | `DELETE /playlists/{id}/items` |

**spotipy mapping:**
- Use `sp.playlist_items()` — NOT `sp.playlist_tracks()` (maps to the removed endpoint).
- `sp.playlist_add_items()` already uses the correct `/items` path.

### Search limit reduced

| Parameter | Old | New |
|---|---|---|
| `limit` maximum | 50 | 10 |
| `limit` default | 20 | 5 |

Always pass `limit` explicitly. SpotyVibe uses `limit=1` for all track searches (sufficient for exact-match lookups).

### Removed endpoints (selection)

- `GET /users/{id}` and `GET /users/{id}/playlists` — use `GET /me/playlists` (`sp.current_user_playlists()`) instead.
- Type-specific library endpoints (`PUT/DELETE /me/albums`, `PUT/DELETE /me/tracks`, etc.) — replaced by `PUT/DELETE /me/library`.
- `GET /browse/categories`, `GET /browse/categories/{id}/playlists`, related browsing endpoints.
- `GET /artists/{id}/related-artists`.

### Removed response fields

| Object | Removed fields |
|---|---|
| Album / Track | `available_markets`, `popularity` |
| Artist | `followers`, `popularity` |
| Show / Audiobook | `available_markets`, `publisher` |
| User | `country`, `email`, `explicit_content`, `followers`, `product` |

### Renamed response fields

| Object | Old field | New field | Notes |
|---|---|---|---|
| Playlist (simplified, from `GET /me/playlists`) | `tracks` | `items` | Summary object `{"href": "...", "total": N}`. Old `tracks` field is now `null`. |
| Playlist item (each entry in `GET /playlists/{id}/items`) | `track` | `item` | The inner key holding the track object. Old `track` key is absent. |

### Playlist item inner key: `track` → `item`

Before February 2026, each entry returned by `sp.playlist_items()` looked like:
```json
{"track": {"uri": "...", "name": "...", ...}}
```
After February 2026, the key is `item`:
```json
{"item": {"uri": "...", "name": "...", ...}}
```

**Impact on field filtering:** When using the `fields` parameter, use `items(item(...))` — not `items(track(...))`. The old filter silently returns empty objects `{}` instead of an error.

**Defensive pattern used in SpotyVibe:**
```python
t = entry.get("item") or entry.get("track")
```
This fallback handles both the current and any cached/legacy responses.

---

## OAuth 2.0 — Authorization Code Flow

SpotyVibe uses the **Authorization Code Flow** (not Client Credentials), which requires the user to grant permission via their browser.

### Required scopes

```
playlist-modify-private playlist-read-private
```

### Redirect URIs

Both URIs must be registered in the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) for the app to work:

| Platform | Redirect URI |
|---|---|
| Desktop | `http://127.0.0.1:5000/callback` |
| Android APK | `spotyvibe://callback` |

**Why two URIs?**
- On desktop, Spotify redirects directly to the Flask server running at `127.0.0.1:5000`.
- On Android, the system browser cannot reach `127.0.0.1:5000` (Flask runs inside the app process). Instead, Spotify redirects to `spotyvibe://callback`, which Android's intent system delivers to `MainActivity` via the `<intent-filter>` in `AndroidManifest.xml`. `MainActivity.handleOAuthIntent()` then extracts the auth code and forwards it to Flask at `http://127.0.0.1:5000/callback`.

**Error "redirect_uri: No matching configuration"** means the URI sent in the OAuth request is not in the Dashboard — add the missing URI.

### Token cache

Spotipy stores the OAuth token at `CACHE_FILE` (`%LOCALAPPDATA%\spotyvibe\.spotify-cache` on desktop, internal app storage on Android). The token is reused and auto-refreshed. Never commit this file.

---

## Endpoints Used by SpotyVibe

| spotipy method | HTTP endpoint | Notes |
|---|---|---|
| `sp.current_user_playlists()` | `GET /me/playlists` | Paginate with `limit=50, offset=N` |
| `sp.current_user_playlist_create()` | `POST /me/playlists` | Creates private playlist |
| `sp.playlist_items()` | `GET /playlists/{id}/items` | Replaces removed `/tracks` (Feb 2026) |
| `sp.playlist_add_items()` | `POST /playlists/{id}/items` | Add tracks by URI |
| `sp.playlist_remove_all_occurrences_of_items()` | `DELETE /playlists/{id}/items` | Remove by URI |
| `sp.search()` | `GET /search` | `type="track"`, `limit=1` (max 10 since Feb 2026) |
| `sp.current_user()` | `GET /me` | Used only for token validation |

### Key rules

- **Always prefer `current_user_*` methods** over the deprecated `user_*` variants (e.g. `current_user_playlists()` not `user_playlists()`).
- **Never use `user_playlist_create()`** — the `POST /v1/users/{user_id}/playlists` endpoint was removed in February 2026. Use `current_user_playlist_create()`.
- **Search `limit` must be ≤ 10** after the February 2026 change.
- Before adding any new Spotify API call, verify the endpoint exists in the [current Spotify Web API Reference](https://developer.spotify.com/documentation/web-api).

---

# Agent Operational Procedures

## Git — Preventing Pager/Interactive Prompts

Some git commands (e.g. `git diff --stat`, `git log`, `git diff`) open a pager (`less`) that blocks the terminal waiting for user input. **Always** prevent this by appending `| cat` or using `git --no-pager`:

```bash
# Either of these works:
git --no-pager diff --stat
git diff --stat | cat

git --no-pager log --oneline -10
git log --oneline -10 | cat
```

Apply this to **any** git command whose output may exceed the terminal height: `diff`, `log`, `show`, `branch -a`, `stash list`, `diff --stat`, etc.

---

## SKILL: git-commit-and-push

When committing and pushing changes, follow this procedure in order:

1. Stage the relevant changed files
2. **Check if any context files need updating:**
   - `.github/workflows/*.yml` changed → regenerate `context/workflows.md`
   - Project structure changed significantly → consider updating `context/architecture.md`
3. Stage any regenerated context files alongside the main changes
4. Commit with a descriptive message following the style defined in `AGENTS.md`
5. Push to remote

Context file updates must be part of the **same commit** as the changes that caused them — never a separate "update context" commit.

---

## SKILL: create-pull-request

To create a Pull Request from `develop` into `main`:

```bash
gh pr create --base main --head develop --fill
```

`--fill` uses the commit log to auto-populate the PR title and body.

---

## Context Files

Context files live in `context/` and are **generated summaries** — do not hand-edit them.

### File format

Every context file must begin with this header block:

```
# <Title>
# Generated: <YYYY-MM-DD>
# Source files:
#   - path/to/source1
#   - path/to/source2
```

The `# Source files:` list is mandatory. It tells future agents exactly which files to re-read when regenerating the summary — without it, the context file is untrustworthy.

### Known context files

| File | Summarizes | Regenerate when |
|---|---|---|
| `context/workflows.md` | `.github/workflows/*.yml` | Any workflow file changes |

### How to regenerate a context file

1. Read all files listed under `# Source files:` in the existing context file
2. Summarize into the format above
3. Update the `# Generated:` date to today
4. Stage and commit as part of the SKILL: git-commit-and-push procedure

# SKILL: Python Project GitHub Release and Tagging Automation

## Overview

This skill describes how to manage automated version tagging and artifact releases for a Python project using GitHub Actions. It is suitable for projects where a version number is defined in a `version.py` file, and releases are organized through Pull Requests (PR), semantic versioning, and dedicated workflows.

---

## 1. Version Management   

- The source of truth for the application version is a `version.py` file in the project root:
  ```python
  __version__ = "1.2.3"  # or "0.5-beta"