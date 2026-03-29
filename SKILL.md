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
