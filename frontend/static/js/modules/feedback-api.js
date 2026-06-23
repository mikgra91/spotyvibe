/**
 * Thin wrappers around `/api/feedback` and `/api/remove`.
 *
 * Centralises the request payload shape (`artist`, `track`, `reason`,
 * `playlist_id`, `track_id`) so all three call sites — discover (feedback.js),
 * review (review.js), and the preview overlay (preview.js) — agree on the
 * field names and the response parsing.
 *
 * Callers still own their toast/dispatch logic because each surface uses
 * subtly different copy ("Disliked & removed" vs "Removed from playlist"
 * etc.) — only the network plumbing is shared.
 */

/**
 * POST /api/feedback.
 *
 * @param {Object}   p
 * @param {'like'|'dislike'} p.action
 * @param {string}   p.artist
 * @param {?string}  p.track       Optional: when null, applies to artist in general.
 * @param {?string}  p.reason      Optional free-form reason.
 * @param {?string}  p.playlistId  Optional Spotify playlist id (target for removal).
 * @param {?string}  p.trackId     Optional Spotify track id (skips text search).
 * @returns {Promise<{ok: boolean, status: number, body: Object, error?: string}>}
 *   On HTTP error, `ok=false` and `error` carries the server-provided detail
 *   (or 'unknown'). On network failure the promise rejects — callers should
 *   wrap the call in try/catch.
 */
export async function postFeedback({ action, artist, track, reason, playlistId, trackId, source }) {
    const resp = await fetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            action,
            artist,
            track:  track  || null,
            reason: reason || null,
            playlist_id: playlistId || null,
            track_id: trackId || null,
            source: source || 'discover',
        }),
    });
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok) {
        return { ok: false, status: resp.status, body, error: body.error || 'unknown' };
    }
    return { ok: true, status: resp.status, body };
}

/**
 * POST /api/remove.
 *
 * @param {Object}  p
 * @param {string}  p.artist
 * @param {string}  p.track
 * @param {?string} p.playlistId
 * @param {?string} p.trackId
 * @returns {Promise<{ok: boolean, status: number, body: Object}>}
 */
export async function postRemove({ artist, track, playlistId, trackId, source }) {
    const resp = await fetch('/api/remove', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            artist,
            track,
            playlist_id: playlistId || null,
            track_id: trackId || null,
            source: source || 'discover',
        }),
    });
    const body = await resp.json().catch(() => ({}));
    return { ok: resp.ok, status: resp.status, body };
}

