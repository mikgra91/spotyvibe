# Spotify Web API — Developer Reference

This document summarises the Spotify Web API endpoints and patterns used by SpotyVibe, including breaking changes introduced in **February 2026**. Consult the [official Spotify Web API Reference](https://developer.spotify.com/documentation/web-api) before making API changes.

> **MCP Server available:** If you are using an AI coding assistant, a Spotify MCP server (`marcelmarais/spotify-mcp-server`) is recommended for live API exploration, verifying response shapes, and testing search queries. See `CLAUDE.md` → "Optional MCP Servers" for setup instructions.

---

## February 2026 Breaking Changes

### Development Mode restrictions (effective March 9, 2026)

Spotify tightened Development Mode access as part of their platform security update:

- **Premium required:** The Spotify app owner must have an active Spotify Premium subscription. If Premium lapses, the app's API access stops working.
- **5-user cap:** Each Client ID is limited to a maximum of 5 authorized users (down from 25). Only the app owner needs Premium — authorized test users do not.
- **Extended Quota Mode** (for public/production apps) now requires a legally registered business, 250,000+ monthly active users, availability in key Spotify markets, and an active launched service.

**Impact on SpotyVibe:** Every user runs their own Spotify Developer App in Development Mode. This means each user must have Spotify Premium to use playlist creation and other write operations via the API.

Sources: [Spotify blog announcement](https://developer.spotify.com/blog/2026-02-06-update-on-developer-access-and-platform-security), [TechCrunch coverage](https://techcrunch.com/2026/02/06/spotify-changes-developer-mode-api-to-require-premium-accounts-limits-test-users/)

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

**Error "redirect_uri: No matching configuration"** means the URI sent in the OAuth request is not in the Dashboard — add the missing URI.

### Token cache

Spotipy stores the OAuth token at `CACHE_FILE` (`%LOCALAPPDATA%\spotyvibe\.spotify-cache` on desktop). The token is reused and auto-refreshed. Never commit this file.

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

Git commands like `log`, `diff`, `show`, `branch -a`, `stash list`, `diff --stat` open an interactive pager (`less`) that blocks the terminal. **Always** use `git --no-pager` to prevent this:

```bash
git --no-pager diff --stat
git --no-pager log --oneline -10
git --no-pager show HEAD
```

**`--no-pager` is mandatory** — do NOT use `| cat` as a substitute. Apply this to every git command whose output may exceed the terminal height.

---

## SKILL: git-commit-and-push

When committing and pushing changes, follow this procedure in order:

1. Stage the relevant changed files
2. Commit with a descriptive message following the style defined in `AGENTS.md`
3. Push to remote

---

## SKILL: create-pull-request

To create a Pull Request from `develop` into `main`:

```bash
gh pr create --base main --head develop --fill
```

`--fill` uses the commit log to auto-populate the PR title and body.

---

# SKILL: Python Project GitHub Release and Tagging Automation

## Overview

This skill describes how to manage automated version tagging and artifact releases for a Python project using GitHub Actions. It is suitable for projects where a version number is defined in a `version.py` file, and releases are organized through Pull Requests (PR), semantic versioning, and dedicated workflows.

---

## 1. Version Management   

- The source of truth for the application version is a `version.py` file in the project root:
  ```python
  __version__ = "1.2.3"  # or "0.5-beta"