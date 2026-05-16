# Spotify Web API — Developer Reference

Conventions and endpoints used by SpotyVibe. Consult the [official Spotify Web API Reference](https://developer.spotify.com/documentation/web-api) before making API changes.

> **MCP Server available:** If you are using an AI coding assistant, a Spotify MCP server (`marcelmarais/spotify-mcp-server`) is recommended for live API exploration, verifying response shapes, and testing search queries. See [`../MCPServers.md`](../MCPServers.md) for setup instructions.

---

## Development Mode access

- **Premium required:** The Spotify app owner must have an active Spotify Premium subscription. If Premium lapses, API access stops working.
- **5-user cap:** Each Client ID is limited to 5 authorized users. Only the app owner needs Premium — authorized test users do not.
- **Daily call ceiling:** Empirically ~1000 search calls per app per 24 h (undocumented; observed via repeated 24 h temp-bans at this threshold). Bulk artist enrichment is not feasible from this tier — SpotyVibe's RAG `top_tracks` field is sourced from Last.fm instead.
- **Extended Quota Mode** (for public/production apps) requires a legally registered business, 250,000+ monthly active users, availability in key Spotify markets, and an active launched service.

**Impact on SpotyVibe:** Every user runs their own Spotify Developer App in Development Mode → each user must have Spotify Premium for playlist writes.

(Originated in the Feb 2026 platform-security update; tightened from previous 25-user cap and looser Premium policy. Sources: [Spotify blog](https://developer.spotify.com/blog/2026-02-06-update-on-developer-access-and-platform-security), [TechCrunch](https://techcrunch.com/2026/02/06/spotify-changes-developer-mode-api-to-require-premium-accounts-limits-test-users/).)

---

## Endpoints used by SpotyVibe

| spotipy method | HTTP endpoint | Notes |
|---|---|---|
| `sp.current_user_playlists()` | `GET /me/playlists` | Paginate with `limit=50, offset=N` |
| `sp.current_user_playlist_create()` | `POST /me/playlists` | Creates private playlist |
| `sp.playlist_items()` | `GET /playlists/{id}/items` | (renamed from `/tracks` in Feb 2026) |
| `sp.playlist_add_items()` | `POST /playlists/{id}/items` | Add tracks by URI |
| `sp.playlist_remove_all_occurrences_of_items()` | `DELETE /playlists/{id}/items` | Remove by URI |
| `sp.search()` | `GET /search` | `type="track"`, `limit=1` (max 10 since Feb 2026) |
| `sp.current_user()` | `GET /me` | Used only for token validation |

### Hard rules

- **Always prefer `current_user_*`** over the deprecated `user_*` variants (e.g. `current_user_playlists()` not `user_playlists()`).
- **Never use `user_playlist_create()`** — the `POST /v1/users/{user_id}/playlists` endpoint was removed in Feb 2026. Use `current_user_playlist_create()`.
- **Search `limit` must be ≤ 10** (max 10, default 5 since Feb 2026). Always pass it explicitly.
- Before adding any new Spotify API call, verify the endpoint exists in the [current Spotify Web API Reference](https://developer.spotify.com/documentation/web-api).

### Removed endpoints to avoid

- `GET /users/{id}` and `GET /users/{id}/playlists` — use `GET /me/playlists` (`sp.current_user_playlists()`) instead.
- Type-specific library endpoints (`PUT/DELETE /me/albums`, `PUT/DELETE /me/tracks`, …) — replaced by `PUT/DELETE /me/library`.
- `GET /browse/categories`, `GET /browse/categories/{id}/playlists`, related browsing endpoints.
- `GET /artists/{id}/related-artists`.

---

## Response-shape gotchas

### Playlist item inner key: `item` (not `track`)

Each entry from `sp.playlist_items()` looks like:
```json
{"item": {"uri": "...", "name": "...", ...}}
```
(Before Feb 2026 the key was `track` — never re-introduce that.)

**Defensive pattern used in SpotyVibe** (handles legacy cached responses):
```python
t = entry.get("item") or entry.get("track")
```

**`fields` parameter must use the new key:** `items(item(uri,name,...))` — not `items(track(...))`. The old filter silently returns empty objects `{}` instead of an error.

### Playlist summary key: `items` (not `tracks`)

`GET /me/playlists` returns each playlist with `items: {"href": "...", "total": N}` instead of the old `tracks` field. Defensive: `pl.get("items") or pl.get("tracks")`.

### Removed response fields

| Object | Removed |
|---|---|
| Album / Track | `available_markets`, `popularity` |
| Artist | `followers`, `popularity` |
| Show / Audiobook | `available_markets`, `publisher` |
| User | `country`, `email`, `explicit_content`, `followers`, `product` |

---

## OAuth 2.0 — Authorization Code Flow

SpotyVibe uses the Authorization Code Flow (not Client Credentials).

**Required scopes:**
```
playlist-modify-private playlist-read-private
```

**Redirect URI:** `http://127.0.0.1:5000/callback` — must be registered in the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).

**Error `redirect_uri: No matching configuration`** = the URI sent in the OAuth request is not in the Dashboard. Add it.

**Token cache:** Spotipy stores the OAuth token at `CACHE_FILE` (`%LOCALAPPDATA%\spotyvibe\.spotify-cache` on desktop). Auto-refreshed. Never commit this file.
