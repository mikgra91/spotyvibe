import os
import sys
import json

# Ensure the spotyvibe package directory is on sys.path so all
# imports resolve correctly regardless of the working directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, Response, render_template, jsonify, request, redirect, stream_with_context
from config import load_config, get_credentials, save_credentials, CREDENTIALS_FILE, BATCH_SIZE, BASE_DIR, get_model, get_settings, get_debug_mode, get_playlist_size, DEBUG_LOG_FILE
import markdown

load_config()

from core.profile import (
    load_profile, save_profile, is_profile_trained,
    get_profile_status, train_profile,
)
from core.suggestions import (
    normalize_history,
    build_messages, call_gpt, update_profile,
    filter_duplicate_suggestions,
)
from core.feedback import like_track, dislike_track
from core.utils import get_openai_models, clear_debug_log
from core.playlist import (
    search_tracks, add_to_playlist, remove_from_playlist,
    get_spotify_auth_status, get_spotify_auth_url, handle_spotify_callback,
    disconnect_spotify,
)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(24)

# Clear debug log on startup so it only contains data from the current session
clear_debug_log()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/help")
def help_content():
    """Return the User Manual rendered as HTML."""
    manual_path = BASE_DIR / "UserManual.md"
    if not manual_path.exists():
        return jsonify({"error": "User manual not found."}), 404
    md_text = manual_path.read_text(encoding="utf-8")
    html = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    return jsonify({"html": html})


def _sse(event_type, **data):
    """Format a single Server-Sent Event line."""
    return f"data: {json.dumps({'type': event_type, **data})}\n\n"


@app.route("/api/run", methods=["POST"])
def run_pipeline():
    """Generate suggestions via OpenAI in batches of BATCH_SIZE, verify on
    Spotify, and repeat until the configured playlist_size is reached.

    Returns an SSE stream so the UI can show real-time progress.
    """

    def generate():
        try:
            if not is_profile_trained():
                yield _sse("error", message="Please train your taste profile first.")
                return

            # Verify Spotify is connected before starting the expensive GPT pipeline
            spotify_status = get_spotify_auth_status()
            if spotify_status != "authenticated":
                yield _sse("error", message="Spotify is not connected. Please connect via ⚙️ Settings first.")
                return

            # Clear debug log at the start of each run so it only
            # contains data from the current generation.
            if get_debug_mode():
                clear_debug_log()

            playlist_size = get_playlist_size()

            yield _sse("progress", message="Loading profile…")
            profile = load_profile()
            normalize_history(profile)

            verified_tracks = []   # tracks with a confirmed Spotify URI
            verified_uris = set()  # fast URI dedup across attempts
            all_not_found = []
            batch_num = 0

            while len(verified_tracks) < playlist_size:
                batch_num += 1
                remaining = playlist_size - len(verified_tracks)
                # Request either a full batch or just the remaining count
                request_count = min(BATCH_SIZE, remaining)

                yield _sse(
                    "progress",
                    message=f"Batch {batch_num}: "
                            f"Asking GPT for {request_count} suggestions… "
                            f"(have {len(verified_tracks)}/{playlist_size})",
                )

                # 1 — Ask GPT for suggestions
                accepted = verified_tracks if batch_num > 1 else None
                messages = build_messages(profile, accepted_tracks=accepted, batch_size=request_count)
                result = call_gpt(messages)

                # 2 — Code-side duplicate / disliked filter
                result = filter_duplicate_suggestions(profile, result)
                if not result["playlist"]:
                    yield _sse(
                        "progress",
                        message=f"Batch {batch_num}: No new suggestions after filtering. Retrying…",
                    )
                    profile = update_profile(profile, result)
                    save_profile(profile)
                    continue

                # 3 — Verify each track exists on Spotify
                batch_count = len(result["playlist"])
                yield _sse(
                    "progress",
                    message=f"Batch {batch_num}: Verifying {batch_count} tracks on Spotify…",
                )
                found, not_found = search_tracks(result["playlist"])
                all_not_found.extend(not_found)

                for t in found:
                    if t["uri"] not in verified_uris:
                        verified_tracks.append(t)
                        verified_uris.add(t["uri"])

                # 4 — Update history
                profile = update_profile(profile, result)
                save_profile(profile)

                yield _sse(
                    "progress",
                    message=f"Batch {batch_num}: {len(found)} found on Spotify, "
                            f"{len(verified_tracks)}/{playlist_size} total verified",
                )

            # Cap at target count
            verified_tracks = verified_tracks[:playlist_size]

            # 5 — Add all verified tracks to the Spotify playlist
            yield _sse("progress", message=f"Adding {len(verified_tracks)} tracks to Spotify playlist…")
            playlist_info = add_to_playlist(verified_tracks)

            # Strip internal "uri" key — the UI doesn't need it
            visible_playlist = [
                {k: v for k, v in t.items() if k != "uri"}
                for t in verified_tracks
            ]

            yield _sse(
                "result",
                playlist=visible_playlist,
                playlist_url=playlist_info.get("url"),
                added=playlist_info.get("added", 0),
                not_found=all_not_found,
            )

        except Exception as e:
            yield _sse("error", message=str(e))

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/feedback", methods=["POST"])
def submit_feedback():
    """Record a like or dislike and persist it in music_profile.json.

    For dislikes the track is also removed from the Spotify playlist.
    """
    data   = request.get_json(force=True)
    action = data.get("action")
    artist = data.get("artist")
    track  = data.get("track")
    reason = data.get("reason")

    if not artist:
        return jsonify({"error": "Artist is required."}), 400
    if action not in ("like", "dislike"):
        return jsonify({"error": "Action must be 'like' or 'dislike'."}), 400

    try:
        removal = None
        if action == "like":
            like_track(artist, track=track, reason=reason)
        else:
            dislike_track(artist, track=track, reason=reason)
            # Also remove the track from the Spotify playlist
            if track:
                removal = remove_from_playlist(artist, track)
            else:
                removal = {"removed": False, "reason": "No track specified"}

        response = {"status": "ok"}
        if removal is not None:
            response["removal"] = removal
        return jsonify(response)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/remove", methods=["POST"])
def remove_track():
    """Remove a track from the Spotify playlist without recording feedback."""
    data   = request.get_json(force=True)
    artist = data.get("artist")
    track  = data.get("track")

    if not artist or not track:
        return jsonify({"error": "Artist and track are required."}), 400

    try:
        result = remove_from_playlist(artist, track)
        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings/credentials", methods=["GET"])
def read_credentials():
    """Return masked credential values and their set/unset status."""
    return jsonify(get_credentials())


@app.route("/api/settings/credentials", methods=["POST"])
def write_credentials():
    """Update one or more credentials.  Only non-empty values are written."""
    data = request.get_json(force=True)
    save_credentials(data)
    return jsonify({"status": "ok", "path": str(CREDENTIALS_FILE)})


@app.route("/api/settings/models")
def list_models():
    """Return available OpenAI chat models and the currently selected one."""
    try:
        models = get_openai_models()
        return jsonify({"models": models, "selected": get_model()})
    except ValueError as e:
        return jsonify({"error": str(e), "models": [], "selected": get_model()}), 400
    except Exception as e:
        return jsonify({"error": str(e), "models": [], "selected": get_model()}), 500


@app.route("/api/settings", methods=["GET"])
def read_settings():
    """Return non-secret settings (model, debug mode)."""
    return jsonify(get_settings())


@app.route("/api/settings", methods=["POST"])
def write_settings():
    """Update non-secret settings (model, debug mode, playlist size)."""
    data = request.get_json(force=True)
    payload = {}
    if "model" in data:
        payload["OPENAI_MODEL"] = data["model"]
    if "debug_mode" in data:
        payload["DEBUG_MODE"] = "true" if data["debug_mode"] else ""
    if "playlist_size" in data:
        payload["PLAYLIST_SIZE"] = str(int(data["playlist_size"]))
    save_credentials(payload)
    return jsonify({"status": "ok"})


@app.route("/api/settings/debug-log", methods=["DELETE"])
def clear_debug_log_endpoint():
    """Clear the debug log file."""
    try:
        if DEBUG_LOG_FILE.exists():
            DEBUG_LOG_FILE.unlink()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Taste profile training ──────────────────────────────────────────

@app.route("/api/profile/status")
def profile_status():
    """Return whether the profile has been trained and when."""
    return jsonify(get_profile_status())


@app.route("/api/train-profile", methods=["POST"])
def train_profile_endpoint():
    """Send the user's taste description to GPT and update the profile."""
    data = request.get_json(force=True)
    user_text = (data.get("text") or "").strip()

    if not user_text:
        return jsonify({"error": "Please describe your music taste."}), 400

    try:
        updated = train_profile(user_text)
        return jsonify({
            "status": "ok",
            "last_updated": updated.get("last_updated"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Spotify authentication ──────────────────────────────────────────

@app.route("/api/spotify/status")
def spotify_status():
    """Return the current Spotify auth state."""
    return jsonify({"status": get_spotify_auth_status()})


@app.route("/api/spotify/auth")
def spotify_auth():
    """Redirect the browser to Spotify's authorization page."""
    return redirect(get_spotify_auth_url())


@app.route("/api/spotify/disconnect", methods=["POST"])
def spotify_disconnect():
    """Clear the cached Spotify token so the user can re-authenticate."""
    disconnect_spotify()
    return jsonify({"status": "ok"})


@app.route("/callback")
def spotify_callback():
    """Handle the OAuth callback from Spotify."""
    error = request.args.get("error")
    code = request.args.get("code")

    page = (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<style>body{{background:#121212;color:#fff;font-family:sans-serif;'
        'text-align:center;padding:4rem 1rem}}'
        'h2{{margin-bottom:.5rem}}p{{color:#b3b3b3;max-width:480px;margin:0 auto}}'
        'a{{color:#1DB954;text-decoration:none}}a:hover{{text-decoration:underline}}'
        'code{{background:#282828;padding:2px 6px;border-radius:4px;font-size:.85em}}'
        '</style></head>'
        '<body><h2 style="color:{colour}">{icon} {title}</h2>'
        '{message}{script}</body></html>'
    )

    close_script = (
        '<script>'
        'if(window.opener){'
        'window.opener.postMessage("spotify-auth-complete","*");'
        'setTimeout(()=>window.close(),1500);'
        '}'
        '</script>'
    )

    if error:
        desc = request.args.get("error_description", "")
        hint = (
            "<p style='margin-top:1.5rem;font-size:.85rem'>"
            "<strong>Common fix:</strong> make sure "
            "<code>http://127.0.0.1:5000/callback</code> "
            "is listed as a Redirect URI in your "
            "<a href='https://developer.spotify.com/dashboard' target='_blank'>"
            "Spotify Developer Dashboard</a>.</p>"
            "<p style='margin-top:1rem'>"
            "<a href='/api/spotify/auth'>↻ Try again</a></p>"
        )
        return page.format(
            colour="#e74c3c", icon="❌", title="Authentication Failed",
            message=f"<p>{error}</p>"
                    + (f"<p>{desc}</p>" if desc else "")
                    + hint,
            script="",
        )

    if code and handle_spotify_callback(code):
        return page.format(
            colour="#1DB954", icon="✅", title="Spotify Connected!",
            message="<p>You can close this window and return to the app.</p>",
            script=close_script,
        )

    return page.format(
        colour="#e74c3c", icon="❌", title="Authentication Failed",
        message="<p>Could not exchange the authorization code. Please try again.</p>"
               "<p style='margin-top:1rem'><a href='/api/spotify/auth'>↻ Try again</a></p>",
        script="",
    )


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", port=5000)

