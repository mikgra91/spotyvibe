# SpotyVibe Android APK — Feasibility Analysis & Implementation Plan

**Date:** 2026-03-27  
**Scope:** Analyse whether the existing SpotyVibe web application can be packaged as an Android APK, and outline the viable paths to achieve it.  
**Chosen approach:** Option B — Embedded Python on Android via Chaquopy (single-user, self-contained).

---

## Current Architecture Summary

| Layer | Technology | Notes |
|---|---|---|
| **Frontend** | Vanilla HTML / CSS / JS (single-page) | Served by Flask via `templates/index.html` + `static/css/styles.css` |
| **Backend** | Python 3.10+ / Flask ≥3.0 | All business logic, API orchestration, SSE streaming |
| **AI** | OpenAI API (via `openai` library) | Called server-side from `core/suggestions.py` and `core/profile.py` |
| **Spotify** | Spotipy (Spotify Web API) | OAuth 2.0 flow, playlist CRUD, parallel track search |
| **Storage** | Local filesystem (`%LOCALAPPDATA%\spotyvibe\`) | `.credentials`, profile JSON, Spotify token cache, debug log |
| **Streaming** | Server-Sent Events (SSE) | Real-time generation progress from `/api/run` |

### Key Constraints for Mobile

1. **Server-side dependency** — all OpenAI and Spotify API calls happen in Python on the server. The frontend is a thin client that only renders results and sends user actions.
2. **File-based storage** — credentials, profile, and Spotify token cache are stored as files in `%LOCALAPPDATA%`, not in a database.
3. **OAuth callback** — Spotify OAuth redirects to `http://127.0.0.1:5000/callback`. This requires a running HTTP server at that address.
4. **SSE streaming** — the frontend consumes `text/event-stream` responses for live progress updates during playlist generation.
5. **Canvas animations** — two theme renderers (Equalizer, Pulse) use `<canvas>` with `requestAnimationFrame`.

---

## Verdict: Is an APK Possible?

**Yes — but the approach depends on where the Python backend runs.**

The frontend (HTML/CSS/JS) is already fully self-contained and mobile-compatible in structure (single page, no framework, `viewport` meta tag present). The challenge is not the APK shell — it is the Flask server that the frontend depends on.

---

## Viable Approaches

### Option A: Cloud-Hosted Backend + Capacitor APK ⭐ Recommended

**Concept:** Deploy the Flask backend to a cloud server. Wrap the frontend in a native Android WebView shell using [Capacitor](https://capacitorjs.com/) (or [Cordova](https://cordova.apache.org/)).

**How it works:**
```
┌──────────────────────┐         ┌──────────────────────┐
│   Android APK        │  HTTPS  │   Cloud Server       │
│   (Capacitor shell)  │────────►│   (Flask backend)    │
│                      │         │                      │
│   WebView loads      │◄────────│   API responses +    │
│   bundled HTML/CSS/JS│   SSE   │   SSE streams        │
└──────────────────────┘         └──────────────────────┘
                                          │
                              ┌───────────┴───────────┐
                              ▼                       ▼
                        OpenAI API             Spotify API
```

| Aspect | Detail |
|---|---|
| **APK contains** | HTML/CSS/JS frontend (bundled), Capacitor runtime |
| **Backend runs on** | Cloud VM / PaaS (e.g. Railway, Render, Fly.io, AWS, VPS) |
| **Code changes needed** | Moderate — see below |
| **Effort estimate** | Medium |
| **Multi-user ready** | Yes (each user authenticates separately) |

#### Required Changes

| # | Area | Change | Complexity |
|---|---|---|---|
| 1 | **API base URL** | Frontend must target the cloud server URL instead of relative paths (`/api/...` → `https://your-server.com/api/...`). Can be injected at build time via an environment variable or a config JS file. | Low |
| 2 | **CORS** | Flask must allow cross-origin requests from the Capacitor WebView origin (`capacitor://localhost` on Android). Add `flask-cors` and whitelist the origin. | Low |
| 3 | **OAuth redirect** | Spotify callback must go to the cloud server (`https://your-server.com/callback`), then redirect back to the app via a deep link or Capacitor's custom URL scheme. Requires updating the Spotify Developer Dashboard redirect URIs. | Medium |
| 4 | **Storage: multi-user** | File-based credential/profile storage assumes a single user. For a cloud deployment, each user needs isolated storage — either per-user directories keyed by a session/user ID, or migration to a lightweight database (SQLite / PostgreSQL). | Medium–High |
| 5 | **Authentication** | A cloud-hosted backend needs user authentication (login system) to prevent unauthorized access to the API and to isolate user data. | Medium–High |
| 6 | **HTTPS** | All traffic must be over HTTPS for mobile security and Spotify OAuth requirements. | Low (most PaaS provide this) |
| 7 | **Capacitor project** | Create a Capacitor project, copy the frontend assets, configure `capacitor.config.ts`, build the APK with Android Studio. | Low–Medium |

#### Pros
- Cleanest separation of concerns
- Works on any device with the APK (no local Python needed)
- Scales to multiple users
- Frontend code barely changes

#### Cons
- Requires hosting infrastructure (cost, maintenance)
- Requires a user authentication system
- Storage model must be reworked for multi-tenancy
- Spotify OAuth deep-link handling adds complexity

---

### Option B: Embedded Python on Android (Chaquopy / Buildozer)

**Concept:** Bundle the entire Python runtime + Flask server inside the APK. The app starts a local Flask server on the device and opens a WebView pointing to `http://127.0.0.1:5000`.

**How it works:**
```
┌────────────────────────────────────────────┐
│              Android APK                   │
│                                            │
│  ┌──────────────────────────────────────┐  │
│  │  WebView → http://127.0.0.1:5000    │  │
│  └──────────────┬───────────────────────┘  │
│                 │                           │
│  ┌──────────────▼───────────────────────┐  │
│  │  Embedded Python (Chaquopy)          │  │
│  │  Flask server running locally        │  │
│  │  All core/ modules run natively      │  │
│  └──────────────┬───────────────────────┘  │
└─────────────────┼──────────────────────────┘
                  │
      ┌───────────┴───────────┐
      ▼                       ▼
 OpenAI API             Spotify API
```

| Aspect | Detail |
|---|---|
| **APK contains** | Python interpreter, all `.py` files, pip dependencies, HTML/CSS/JS |
| **Backend runs on** | Locally on the Android device |
| **Tooling** | [Chaquopy](https://chaquo.com/chaquopy/) (Gradle plugin, embeds CPython in Android) or [Buildozer](https://buildozer.readthedocs.io/) (Kivy toolchain, uses python-for-android) |
| **Code changes needed** | Moderate |
| **Effort estimate** | Medium–High |
| **Multi-user ready** | No (single-user, runs locally) |

#### Required Changes

| # | Area | Change | Complexity |
|---|---|---|---|
| 1 | **Storage paths** | Replace `%LOCALAPPDATA%` paths with Android-appropriate paths (app-internal storage via `Context.getFilesDir()`). In `config.py`, detect the platform and switch paths. | Low–Medium |
| 2 | **OAuth redirect** | `http://127.0.0.1:5000/callback` actually works on-device since Flask is running locally. However, the Android WebView or Custom Tab must be configured to handle the redirect. Spotify Developer Dashboard must whitelist `http://127.0.0.1:5000/callback`. | Medium |
| 3 | **Startup sequence** | The Android app must start the Flask server in a background thread before loading the WebView. Need a small Kotlin/Java entrypoint that boots Python and waits for the server to be ready. | Medium |
| 4 | **Dependency compatibility** | All pip packages (`spotipy`, `openai`, `flask`, `python-dotenv`, `markdown`) must compile on Android/ARM. Pure-Python packages are fine; any C-extension packages need cross-compilation (Chaquopy handles most common ones). | Low (all current deps are pure-Python or Chaquopy-supported) |
| 5 | **APK size** | Bundling CPython + packages will make the APK 30–80 MB. Acceptable for a utility app. | N/A (informational) |
| 6 | **Lifecycle management** | Flask server must start/stop with the Android app lifecycle. Handle `onPause`/`onResume` to avoid battery drain. | Medium |

#### Pros
- Fully self-contained — no external server needed
- Single-user model stays intact (no auth system needed)
- Credentials stay on-device (better privacy)
- Closest to the current architecture

#### Cons
- Large APK size (30–80 MB due to Python runtime)
- Slower cold start (Python interpreter boot time)
- Chaquopy requires an Android Studio project and Gradle integration
- Buildozer/python-for-android has a steeper learning curve and more build issues
- Performance on low-end devices may be poor

---

### Option C: Progressive Web App (PWA)

**Concept:** Add a service worker and web app manifest to the existing Flask app so users can "install" it on their Android home screen. Not a true APK, but provides an app-like experience.

**How it works:**
```
┌──────────────────────┐         ┌──────────────────────┐
│   Android (Chrome)   │  HTTPS  │   Cloud Server or    │
│   "Installed" PWA    │────────►│   Local network      │
│                      │         │   (Flask backend)    │
│   Renders in browser │◄────────│                      │
│   engine (no WebView)│         │                      │
└──────────────────────┘         └──────────────────────┘
```

| Aspect | Detail |
|---|---|
| **Installed via** | Chrome's "Add to Home Screen" or "Install App" prompt |
| **Backend runs on** | Cloud server (same as Option A) **or** the user's PC on the same network |
| **Code changes needed** | Small |
| **Effort estimate** | Low |

#### Required Changes

| # | Area | Change | Complexity |
|---|---|---|---|
| 1 | **Web App Manifest** | Add `manifest.json` with app name, icons, theme color, `display: standalone`. | Low |
| 2 | **Service Worker** | Add a basic service worker for offline asset caching (CSS, JS, fonts). API calls still require network. | Low |
| 3 | **Icons** | Create app icons in required sizes (192×192, 512×512). | Low |
| 4 | **HTTPS** | Required for service worker registration. Needed if hosted remotely. | Low |

#### Pros
- Minimal code changes
- No Capacitor/Android Studio needed
- Works on iOS too
- Standard web technology

#### Cons
- **Not a real APK** — cannot be distributed via Google Play Store
- Still requires the Flask backend running somewhere
- Limited access to device APIs (though SpotyVibe doesn't need them)
- Some browsers have inconsistent PWA support
- User must use Chrome and know how to "install" a web app

---

### Option D: TWA (Trusted Web Activity)

**Concept:** A Trusted Web Activity wraps a PWA in a thin Android APK that runs in Chrome's rendering engine (not a WebView). This is Google's official way to put a PWA on the Play Store.

| Aspect | Detail |
|---|---|
| **Combines** | PWA (Option C) + APK wrapper |
| **Requires** | PWA with valid manifest + service worker + HTTPS |
| **Tooling** | [Bubblewrap](https://github.com/GoogleChromeLabs/bubblewrap) or Android Studio TWA template |
| **Effort** | Low (on top of a working PWA) |

Essentially Option C + a thin APK shell. Same backend requirements as Option A (cloud-hosted).

---

## Approach Comparison Matrix

| Criteria | A: Cloud + Capacitor | B: Embedded Python | C: PWA | D: TWA |
|---|---|---|---|---|
| **True APK** | ✅ Yes | ✅ Yes | ❌ No | ✅ Yes |
| **Play Store distributable** | ✅ Yes | ✅ Yes | ❌ No | ✅ Yes |
| **No external server needed** | ❌ Needs cloud | ✅ Self-contained | ❌ Needs server | ❌ Needs server |
| **Code changes** | Moderate | Moderate | Small | Small + PWA setup |
| **Multi-user** | ✅ Yes | ❌ Single user | Depends on backend | Depends on backend |
| **APK size** | ~5 MB | ~30–80 MB | N/A | ~2 MB |
| **Cold start speed** | Fast | Slow (Python boot) | Fast | Fast |
| **Privacy (keys on-device)** | ❌ Keys on server | ✅ Keys on device | ❌ Keys on server | ❌ Keys on server |
| **Ongoing hosting cost** | Yes | No | Yes (if cloud) | Yes |
| **Build complexity** | Medium | Medium–High | Low | Low–Medium |
| **Offline capability** | ❌ No (needs API) | ❌ No (needs API) | ❌ No (needs API) | ❌ No (needs API) |

> **Note:** None of the options provide true offline capability because SpotyVibe fundamentally requires network access to the OpenAI and Spotify APIs.

---

## Recommendation

### For personal use (single user, no Play Store): **Option B (Embedded Python)**

This preserves the current single-user, credentials-on-device architecture with the fewest conceptual changes. The user runs the entire app self-contained on their phone. No server, no hosting costs, no authentication system.

**Best tooling choice:** [Chaquopy](https://chaquo.com/chaquopy/) — it is the most mature and well-documented solution for embedding Python in Android apps via Gradle/Android Studio. All current pip dependencies are pure-Python or supported.

### For distribution to other users: **Option A (Cloud + Capacitor)**

If the goal is distributing the app to other people, a cloud backend is unavoidable — you cannot ask each user to manage their own Python server. This requires the most architectural changes (multi-user storage, authentication) but produces the most professional result.

### For quick experiment / lowest effort: **Option C (PWA)**

If you just want app-like behavior on your phone without building an APK, a PWA can be added to the existing project in under an hour. The Flask server would need to be accessible over your local network or hosted somewhere.

---

## Next Steps (If Proceeding)

Whichever option is chosen, the implementation would follow this general sequence:

1. **Decide on the approach** (A, B, C, or D)
2. **Address styling for mobile** (separate topic, as noted — responsive layout, touch targets, viewport handling)
3. **Implement the required backend changes** (storage paths, CORS, OAuth flow)
4. **Set up the APK build pipeline** (Capacitor / Chaquopy / Bubblewrap)
5. **Test on a real Android device / emulator**
6. **Iterate on mobile-specific UX issues**

---

*This document is an analysis only. No code changes have been made.*

---
---

# Option B — Detailed Implementation Plan

## Table of Contents

1. [How It Works (High-Level)](#1-how-it-works-high-level)
2. [Storage on Android — Credentials & Profile](#2-storage-on-android--credentials--profile)
3. [Spotify OAuth on Android](#3-spotify-oauth-on-android)
4. [Project Structure](#4-project-structure)
5. [Step-by-Step Implementation Plan](#5-step-by-step-implementation-plan)
6. [Build Scripts & APK Generation](#6-build-scripts--apk-generation)
7. [Testing & Debugging](#7-testing--debugging)
8. [Risks & Mitigations](#8-risks--mitigations)

---

## 1. How It Works (High-Level)

The APK bundles the full CPython interpreter (via Chaquopy), all Python source files, and all pip dependencies inside a native Android app. On launch:

```
┌───────────────────────────────────────────────────────┐
│                    Android APK                        │
│                                                       │
│  1. MainActivity (Kotlin)                             │
│     └─ starts Python in a background thread           │
│        └─ runs Flask on 127.0.0.1:5000                │
│                                                       │
│  2. WebView                                           │
│     └─ loads http://127.0.0.1:5000                    │
│     └─ renders the full SpotyVibe UI                  │
│     └─ all fetch() / SSE calls go to localhost        │
│                                                       │
│  3. Python runtime (Chaquopy)                         │
│     └─ Flask + all core/ modules                      │
│     └─ openai, spotipy, python-dotenv, markdown       │
│     └─ File I/O uses Android internal storage         │
└───────────────────────────────────────────────────────┘
         │                        │
         ▼                        ▼
    OpenAI API              Spotify API
   (over HTTPS)            (over HTTPS)
```

The user experience is identical to the desktop version — the same HTML/CSS/JS renders in the Android WebView. All API calls stay on `localhost`, so there is no network latency between frontend and backend.

---

## 2. Storage on Android — Credentials & Profile

### Current Desktop Storage

On Windows, all user data lives in `%LOCALAPPDATA%\spotyvibe\`:

| File | Purpose | Current path resolution |
|---|---|---|
| `.credentials` | API keys, settings (dotenv format) | `Path(os.environ["LOCALAPPDATA"]) / "spotyvibe"` |
| `.spotify-cache` | Spotify OAuth token (JSON) | Same directory |
| `personalized_music_profile.json` | Taste profile | Same directory |
| `personalized_music_profile.history.json` | Profile backup | Same directory |
| `debug.log` | GPT debug log | Same directory |

### How It Will Work on Android

On Android, `%LOCALAPPDATA%` does not exist. The `config.py` fallback (`os.path.expanduser("~")`) would resolve to a non-writable or unpredictable location.

**Solution:** Detect the Android platform and use the **app-internal storage** directory, which is:
- Private to the app (no other app can access it)
- No permissions required (no `READ_EXTERNAL_STORAGE` / `WRITE_EXTERNAL_STORAGE`)
- Survives app updates (only cleared on uninstall)
- Path: `/data/data/com.spotyvibe.app/files/spotyvibe/`

#### Code Change in `config.py`

The existing `_APP_DIR` computation:

```python
# Current
_APP_DIR = Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))) / "spotyvibe"
```

Becomes platform-aware:

```python
import sys

def _get_app_dir():
    """Return the platform-appropriate storage directory."""
    if hasattr(sys, 'getandroidapilevel'):
        # Running inside Chaquopy on Android — use the files dir
        # passed from Kotlin via environment variable
        android_files = os.environ.get("SPOTYVIBE_FILES_DIR")
        if android_files:
            return Path(android_files) / "spotyvibe"
        # Fallback: use the Python home directory (Chaquopy sets this)
        return Path(os.path.expanduser("~")) / "spotyvibe"
    # Desktop (Windows / macOS / Linux)
    return Path(os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))) / "spotyvibe"

_APP_DIR = _get_app_dir()
```

The Kotlin `MainActivity` will set the `SPOTYVIBE_FILES_DIR` environment variable to `context.filesDir.absolutePath` before starting Python. This gives `config.py` a reliable, writable, private storage path.

#### What Happens to Each File on Android

| File | Android location | Notes |
|---|---|---|
| `.credentials` | `/data/data/com.spotyvibe.app/files/spotyvibe/.credentials` | Same dotenv format, same read/write logic. Private to app. |
| `.spotify-cache` | `/data/data/com.spotyvibe.app/files/spotyvibe/.spotify-cache` | Spotipy reads/writes this as before. |
| `personalized_music_profile.json` | `/data/data/com.spotyvibe.app/files/spotyvibe/personalized_music_profile.json` | No changes to profile.py I/O logic. |
| `debug.log` | `/data/data/com.spotyvibe.app/files/spotyvibe/debug.log` | Same behavior. |

#### Security Comparison

| Aspect | Desktop (Windows) | Android |
|---|---|---|
| **Who can read the files?** | Any process running as the same Windows user | Only this app (Android sandboxing) |
| **Encryption at rest?** | No (unless BitLocker is on) | No (unless device is encrypted, which most modern phones are by default) |
| **Survives uninstall?** | Yes (files stay in AppData) | No (app-internal storage is deleted on uninstall) |
| **Backup** | Manual | Android Auto Backup can include it (configurable) |

> **Important:** On uninstall, all credentials and the taste profile will be deleted. If the user wants to preserve their profile across reinstalls, a manual export/import feature could be added later (not in scope for the initial build).

---

## 3. Spotify OAuth on Android

### How It Currently Works (Desktop)

1. User clicks "Connect to Spotify" → Flask returns the Spotify auth URL
2. JavaScript opens a **popup window** (`window.open(...)`) pointing to the auth URL
3. User logs in on Spotify's website and grants permissions
4. Spotify redirects to `http://127.0.0.1:5000/callback`
5. Flask handles the callback → stores the token in `.spotify-cache`
6. The callback page uses `window.opener.postMessage("spotify-auth-complete", "*")` to notify the main page, then auto-closes

### How It Will Work on Android

The same flow works on Android because Flask is running locally on `127.0.0.1:5000`. The key difference is WebView handling:

**Approach: Open Spotify auth in the system browser (Chrome), callback returns to WebView.**

1. When the WebView encounters the Spotify auth URL (external domain `accounts.spotify.com`), the app intercepts it and opens it in **Chrome Custom Tabs** or the default browser.
2. User authenticates on Spotify in Chrome.
3. Spotify redirects to `http://127.0.0.1:5000/callback`.
4. Android routes this back to the WebView (since our Flask server is listening on that address).
5. Flask processes the callback and stores the token — same as desktop.

#### WebView Configuration Required

```kotlin
webView.webViewClient = object : WebViewClient() {
    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
        val url = request.url.toString()
        // External URLs (Spotify auth) → open in system browser
        if (!url.startsWith("http://127.0.0.1:5000")) {
            val intent = Intent(Intent.ACTION_VIEW, request.url)
            startActivity(intent)
            return true  // We handled it
        }
        return false  // Let WebView handle localhost URLs normally
    }
}
```

#### Spotify Developer Dashboard

The redirect URI `http://127.0.0.1:5000/callback` **does not need to change**. Spotify allows localhost redirect URIs, and since Flask is running locally on the device, the redirect works identically.

> **⚠️ Review note — popup window blocker:** The current desktop OAuth flow uses `window.open()` to launch a popup for Spotify login. **Android WebView does not support popup windows by default.** This is a real blocker that is not addressed in the plan. Two possible solutions:
> 1. Override `WebChromeClient.onCreateWindow()` to handle the popup request and route it to the system browser.
> 2. Detect the Android platform on the frontend (e.g. via user-agent or a config flag injected by Flask) and use direct navigation (`window.location.href`) instead of `window.open()`.
>
> Either way, the `window.opener.postMessage()` callback mechanism used by the desktop popup will not work from the system browser back to the WebView. An alternative signalling mechanism is needed — e.g. polling `/api/spotify-status` from the main page after returning from the browser, or using an Android intent filter to intercept the callback URL and reload the WebView.

---

## 4. Project Structure

A new `android/` directory will be added **alongside** the existing project (the desktop version remains untouched):

```
spotyvibe/
├── app.py                      # ← Existing (shared with Android)
├── config.py                   # ← Modified (platform detection added)
├── core/                       # ← Existing (shared)
├── prompts/                    # ← Existing (shared)
├── data/                       # ← Existing (shared)
├── static/                     # ← Existing (shared)
├── templates/                  # ← Existing (shared)
├── tests/                      # ← Existing (desktop tests)
├── requirements.txt            # ← Existing (desktop)
│
└── android/                    # ← NEW: Android project
    ├── build_apk.sh            # One-command build script
    ├── gradle.properties       # Gradle settings
    ├── build.gradle            # Root Gradle build file
    ├── settings.gradle         # Gradle project settings
    ├── local.properties        # SDK path (auto-generated / user-specific)
    │
    └── app/
        ├── build.gradle        # App-level Gradle (Chaquopy config here)
        ├── src/
        │   └── main/
        │       ├── AndroidManifest.xml
        │       ├── kotlin/com/spotyvibe/app/
        │       │   └── MainActivity.kt
        │       ├── res/
        │       │   ├── layout/
        │       │   │   └── activity_main.xml
        │       │   ├── values/
        │       │   │   └── strings.xml
        │       │   └── mipmap-*/
        │       │       └── ic_launcher.png    # App icons
        │       └── python/                    # ← Chaquopy copies Python files here
        │           └── (symlinks or copies of app.py, config.py, core/, etc.)
        └── proguard-rules.pro
```

### How Chaquopy Bundles the Python Code

Chaquopy has two mechanisms:
1. **`src/main/python/`** — Python source files placed here are bundled into the APK and importable from the embedded interpreter.
2. **`pip { install ... }`** — In `app/build.gradle`, you declare pip dependencies and Chaquopy downloads pre-built wheels for Android/ARM at build time.

The build script will **copy** (not symlink — Windows compatibility) the Python source files from the project root into `android/app/src/main/python/` before each build.

---

## 5. Step-by-Step Implementation Plan

### Phase 1: Prepare the Python Codebase (Platform Compatibility)

| Step | File(s) | Change | Details | Status |
|---|---|---|---|---|
| 1.1 | `config.py` | Add Android platform detection | Added `IS_ANDROID` flag via `sys.getandroidapilevel`, `_get_app_dir()` with `SPOTYVIBE_FILES_DIR` env var. | ✅ Done |
| 1.2 | `config.py` | Guard `_OLD_ENV_FILE` migration | Migration now guarded with `if not IS_ANDROID`. | ✅ Done |
| 1.3 | `core/playlist.py` | No change needed | `REDIRECT_URI` stays as `http://127.0.0.1:5000/callback`. Verified. | ✅ Verified |
| 1.4 | `app.py` | Add `host` parameter + disable reloader | Added `host="127.0.0.1"` and `use_reloader=False if IS_ANDROID else None`. Both `__main__` and Kotlin invocation paths covered. | ✅ Done |
| 1.5 | All Python files | Verify pure-Python deps | All deps confirmed Chaquopy-compatible. | ✅ Verified |

> **✅ Review note resolved:** `use_reloader=False` is now set conditionally via `IS_ANDROID` in `app.py`. The Kotlin `MainActivity.kt` also passes `use_reloader=false` when calling `app.run()` directly, so both invocation paths are covered.

**Desktop impact:** None. The platform detection is additive — existing behavior is the `else` branch. **Confirmed: 163 tests pass.**

### Phase 2: Create the Android Project

| Step | What | Details | Status |
|---|---|---|---|
| 2.1 | Create `android/` directory structure | Full structure created as shown in Section 4. | ✅ Done |
| 2.2 | Configure root `build.gradle` | Chaquopy 15.0.1, Kotlin 1.9.22, AGP 8.2.2. | ✅ Done |
| 2.3 | Configure `app/build.gradle` | `minSdk 26`, `targetSdk 34`, Python 3.10, pip deps, `arm64-v8a` only. | ✅ Done |
| 2.4 | Write `AndroidManifest.xml` | `INTERNET` + `ACCESS_NETWORK_STATE` permissions, `usesCleartextTraffic` for localhost. | ✅ Done |
| 2.5 | Write `activity_main.xml` | FrameLayout with splash screen + WebView. | ✅ Done |
| 2.6 | Write `MainActivity.kt` | Flask in daemon thread, splash screen, WebView with OAuth popup support. | ✅ Done |
| 2.7 | Create app icons | Generate `mipmap` icons from a SpotyVibe logo/placeholder. | ⬜ Not done |

> **✅ Review note resolved:** `ACCESS_NETWORK_STATE` was included in the manifest.

#### 5.1 — `MainActivity.kt` Responsibilities

```
onCreate():
  1. Set SPOTYVIBE_FILES_DIR environment variable → context.filesDir
  2. Start Python/Flask in a background thread:
       - Import chaquopy's Python module
       - Execute: "from app import app; app.run(host='127.0.0.1', port=5000, use_reloader=False)"
  3. Wait for Flask to be ready (poll http://127.0.0.1:5000/ with retry)
  4. Show a splash/loading screen during startup
  5. Load WebView → http://127.0.0.1:5000
  6. Configure WebView:
       - Enable JavaScript
       - Enable DOM storage (for localStorage — theme preference)
       - Set WebViewClient to intercept external URLs (Spotify auth → system browser)
       - Set WebChromeClient for console.log forwarding (debugging)

onDestroy():
  1. Flask thread is a daemon thread — dies automatically when the app process exits
  2. No explicit shutdown needed

> **✅ Review note resolved:** The Flask server runs in a Kotlin `Thread` with `isDaemon = true`. When the Android app process exits, the daemon thread is killed automatically. No `werkzeug.server.shutdown` needed. `SPOTYVIBE_FILES_DIR` is set via `os.environ.__setitem__()` in Python before the Flask module is imported.

onBackPressed():
  1. If WebView can go back → webView.goBack()
  2. Otherwise → default behavior (exit)
```

### Phase 3: Build Script & Automation

| Step | What | Details | Status |
|---|---|---|---|
| 3.1 | Create `android/build_apk.sh` | One-command script: copies Python sources + runs `./gradlew assembleDebug`. Copy logic is integrated (no separate script needed). | ✅ Done |
| 3.2 | Create `android/copy_python_sources.sh` | Merged into `build_apk.sh` — source copy is the first step of the build. | ✅ Done (merged) |
| 3.3 | Add `.gitignore` for Android | Ignores `.gradle/`, `app/build/`, `app/src/main/python/`, `local.properties`, APKs/AABs. | ✅ Done |

### Phase 4: Testing

| Step | What | Details | Status |
|---|---|---|---|
| 4.1 | Desktop regression | 163 tests pass (157 original + 6 new platform detection tests). | ✅ Done |
| 4.2 | Android emulator test | Build debug APK, install on emulator (API 26+), verify Flask boots and UI loads. | ⬜ Not done |
| 4.3 | Credential flow test | Enter OpenAI key and Spotify credentials in the Settings UI on Android, verify they persist across app restarts. | ⬜ Not done |
| 4.4 | Spotify OAuth test | Connect to Spotify from the Android app, verify the redirect flow works through the system browser. | ⬜ Not done |
| 4.5 | Generation pipeline test | Run a full playlist generation on Android, verify SSE streaming and Spotify playlist creation. | ⬜ Not done |

---

## 6. Build Scripts & APK Generation

### Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| **Android Studio** | 2024.x+ | Or standalone Android SDK command-line tools |
| **Android SDK** | API 34 | Install via Android Studio SDK Manager |
| **JDK** | 17 | Required by AGP (Android Gradle Plugin) 8.x |
| **Gradle** | 8.x | Bundled with the project via Gradle Wrapper |

### `android/build_apk.sh` — One-Command Build

```bash
#!/bin/bash
# Build the SpotyVibe Android APK
# Usage: cd android && ./build_apk.sh [debug|release]

set -e

BUILD_TYPE="${1:-debug}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_DEST="$SCRIPT_DIR/app/src/main/python"

echo "=== SpotyVibe Android Build ==="
echo "Build type: $BUILD_TYPE"
echo "Project root: $PROJECT_ROOT"

# 1. Clean and recreate the Python source directory
echo "Copying Python sources..."
rm -rf "$PYTHON_DEST"
mkdir -p "$PYTHON_DEST"

# 2. Copy Python files (preserving directory structure)
cp "$PROJECT_ROOT/app.py" "$PYTHON_DEST/"
cp "$PROJECT_ROOT/config.py" "$PYTHON_DEST/"
cp -r "$PROJECT_ROOT/core" "$PYTHON_DEST/"
cp -r "$PROJECT_ROOT/prompts" "$PYTHON_DEST/"
cp -r "$PROJECT_ROOT/data" "$PYTHON_DEST/"
cp -r "$PROJECT_ROOT/static" "$PYTHON_DEST/"
cp -r "$PROJECT_ROOT/templates" "$PYTHON_DEST/"

# Remove __pycache__ directories
find "$PYTHON_DEST" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

echo "Python sources copied to $PYTHON_DEST"

# 3. Build the APK
echo "Building APK..."
cd "$SCRIPT_DIR"

if [ "$BUILD_TYPE" = "release" ]; then
    ./gradlew assembleRelease
    APK_PATH="app/build/outputs/apk/release/app-release.apk"
else
    ./gradlew assembleDebug
    APK_PATH="app/build/outputs/apk/debug/app-debug.apk"
fi

if [ -f "$APK_PATH" ]; then
    echo ""
    echo "=== BUILD SUCCESSFUL ==="
    echo "APK: $SCRIPT_DIR/$APK_PATH"
    echo "Size: $(du -h "$APK_PATH" | cut -f1)"
else
    echo "ERROR: APK not found at expected path"
    exit 1
fi
```

### `android/app/build.gradle` — Chaquopy Configuration (Key Sections)

```groovy
plugins {
    id 'com.android.application'
    id 'org.jetbrains.kotlin.android'
    id 'com.chaquo.python'
}

android {
    namespace 'com.spotyvibe.app'
    compileSdk 34

    defaultConfig {
        applicationId "com.spotyvibe.app"
        minSdk 26          // Android 8.0+ (covers ~95% of active devices)
        targetSdk 34
        versionCode 1
        versionName "1.0"

        // Chaquopy configuration
        python {
            version "3.10"

            pip {
                install "flask>=3.0,<4.0"
                install "openai>=1.0,<3.0"
                install "spotipy>=2.23,<3.0"
                install "python-dotenv>=1.0,<2.0"
                install "markdown>=3.4,<4.0"
            }
        }

        ndk {
            abiFilters "arm64-v8a", "armeabi-v7a"   // ARM only (covers all phones)
        }
    }
}
```

> **⚠️ Review note — APK size optimisation:** Bundling two ABIs (`arm64-v8a` + `armeabi-v7a`) will push the APK toward the higher end of the 30–80 MB estimate. For **personal sideloading**, consider building only `arm64-v8a` — virtually all modern phones (2018+) are 64-bit, and this would significantly reduce APK size. For **Play Store distribution**, use an Android App Bundle (AAB) instead of a raw APK — Google Play will split by ABI automatically, so each user downloads only the libraries for their architecture.

### How to Install the APK on a Phone

```bash
# After build_apk.sh completes:

# Option 1: ADB (USB debugging enabled on phone)
adb install android/app/build/outputs/apk/debug/app-debug.apk

# Option 2: Transfer the APK file to the phone and open it
#           (requires "Install from unknown sources" enabled)
```

---

## 7. Testing & Debugging

### Debugging the Embedded Python

- **Logcat:** `MainActivity.kt` will forward Python `print()` and Flask logs to Android Logcat. Filter with tag `SpotyVibe`.
- **WebView console:** `WebChromeClient.onConsoleMessage()` forwards JavaScript `console.log` to Logcat.
- **Debug mode:** The existing Settings → Debug Mode toggle writes to `debug.log` inside app-internal storage. Can be pulled via `adb`:
  ```bash
  adb shell run-as com.spotyvibe.app cat files/spotyvibe/debug.log
  ```

### Common Issues to Watch For

| Issue | Cause | Mitigation |
|---|---|---|
| Slow cold start (3–8 seconds) | Python interpreter boot + Flask init | Show a splash screen / loading animation |
| WebView shows blank page | Flask not ready yet when WebView loads | Poll `127.0.0.1:5000` in a loop before loading WebView |
| Spotify OAuth fails | System browser can't reach `127.0.0.1:5000/callback` | Verify Flask is bound to `127.0.0.1` (not `0.0.0.0`) and the redirect works in Chrome |
| SSE stream drops | Android may kill background network connections | WebView keeps the connection alive; Flask runs in-process so this is local I/O, not network |
| Large APK size | Python runtime + dependencies | Expected 30–60 MB. ABI filtering to ARM only reduces size. |

> **⚠️ Review note — SSE in WebView:** While SSE via `EventSource` is supported on API 26+, Android WebView has known issues with connection timeouts and aggressively closing idle connections. Since SpotyVibe's SSE stream is short-lived (active only during generation), this should be fine in practice — but it should be a **high-priority test item** on real devices. If issues arise, a fallback to polling `/api/run-status` could be implemented.

---

## 8. Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| **Chaquopy licensing** | Low | Free for open-source. Paid license needed for closed-source ($50/year). SpotyVibe is personal use — choose appropriate license. |

> **⚠️ Review note:** As of recent Chaquopy versions, the community edition is free regardless of open/closed-source status. Double-check the current licensing terms at [chaquo.com/chaquopy](https://chaquo.com/chaquopy/) before assuming a paid license is needed.
| **Python boot time** | Medium | Show a native splash screen. Typical boot is 2–5s on modern devices. |
| **Chaquopy version lag** | Low | Chaquopy supports Python 3.8–3.13. Current project uses 3.10 which is fully supported. |
| **Battery drain** | Medium | Flask runs only while the app is in the foreground. On `onPause`, stop the server or let Android manage it. The app doesn't do background work. |
| **Android WebView quirks** | Low | Test SSE streaming, `localStorage`, and `<canvas>` animations in Android WebView. All are well-supported on API 26+. |
| **Spotify token persistence** | Low | Spotipy's `cache_path` parameter works with any writable file path. Already tested on multiple platforms. |
| **Profile loss on uninstall** | Low | Document this for the user. A future enhancement could add profile export/import. |

---

## Summary of Code Changes Required

| File | Type of Change | Backward Compatible? | Status |
|---|---|---|---|
| `config.py` | Added `IS_ANDROID`, `_get_app_dir()`, guarded `.env` migration | ✅ Yes — desktop path is the `else` branch | ✅ Done |
| `app.py` | Added `IS_ANDROID` import, `host="127.0.0.1"`, `use_reloader=False` on Android | ✅ Yes — `None` on desktop (Flask default) | ✅ Done |
| `core/playlist.py` | No changes | ✅ N/A | — |
| `core/profile.py` | No changes | ✅ N/A | — |
| `core/suggestions.py` | No changes | ✅ N/A | — |
| `core/feedback.py` | No changes | ✅ N/A | — |
| `core/utils.py` | No changes | ✅ N/A | — |
| `templates/index.html` | No changes | ✅ N/A | — |
| `static/css/styles.css` | Mobile responsive styles added (separate commit) | ✅ Yes — `@media` scoped | ✅ Done |
| `tests/test_config.py` | Added 6 tests for platform detection | ✅ Yes | ✅ Done |

**New files (all in `android/`):**

| File | Status |
|---|---|
| `build.gradle` (root) | ✅ Done |
| `settings.gradle` | ✅ Done |
| `gradle.properties` | ✅ Done |
| `gradle/wrapper/gradle-wrapper.properties` | ✅ Done |
| `app/build.gradle` | ✅ Done |
| `app/proguard-rules.pro` | ✅ Done |
| `app/src/main/AndroidManifest.xml` | ✅ Done |
| `app/src/main/res/layout/activity_main.xml` | ✅ Done |
| `app/src/main/res/values/strings.xml` | ✅ Done |
| `app/src/main/kotlin/.../MainActivity.kt` | ✅ Done |
| `build_apk.sh` | ✅ Done |
| `.gitignore` | ✅ Done |
| App icons (`mipmap-*`) | ⬜ Not done |

---

## Remaining Work

- ⬜ **App icons** — Generate mipmap launcher icons in required densities
- ⬜ **Android emulator test** — Build the APK and verify Flask boots, UI loads, and all flows work
- ⬜ **Spotify OAuth test** — Verify the popup → system browser → callback flow on Android
- ⬜ **SSE streaming test** — Verify EventSource works in Android WebView
- ⬜ **Full end-to-end test** — Generate a playlist from the Android app

---

*Phase 1 (Python prep), Phase 2 (Android scaffolding), and Phase 3 (build scripts) are complete. Phase 4 (on-device testing) is pending.*
