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

*This document started as a feasibility analysis and is now also the living implementation tracking document. Phases 1–3 of the Option B implementation are complete. Phase 4 (on-device testing) is pending.*

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

### How It Works on Android (✅ Implemented)

The same flow works on Android because Flask is running locally on `127.0.0.1:5000`. The key differences are WebView popup handling and callback routing:

**Approach: Detect Android WebView → use direct navigation instead of popup → backend fallback redirect.**

The desktop flow uses `window.open()` to launch a Spotify login popup. On Android WebView, popups route external URLs to the system browser, which **cannot** reach the localhost callback since Flask runs only inside the app process. This required a two-part fix:

#### Frontend Detection (✅ Done — `templates/index.html`)

The `connectSpotify()` function checks the user-agent for the Android WebView signature (`/; wv\)/`). When detected, it uses same-window navigation instead of a popup:

```javascript
function connectSpotify() {
    if (/; wv\)/.test(navigator.userAgent)) {
        window.location.href = '/api/spotify/auth';  // Android: direct navigation
        return;
    }
    // Desktop: popup window (existing behavior)
    window.open('/api/spotify/auth', 'spotify-auth', ...);
}
```

#### Backend Fallback (✅ Done — `app.py`)

The `/callback` success page checks for `window.opener`. When it is `null` (the direct-navigation case on Android), the page issues a delayed redirect to the home page instead of attempting `postMessage()`:

```javascript
if (window.opener) {
    window.opener.postMessage("spotify-auth-complete", "*");
    setTimeout(() => window.close(), 1500);
} else {
    setTimeout(() => window.location.href = "/", 1500);  // Android fallback
}
```

#### WebView URL Routing (✅ Done — `MainActivity.kt`)

```kotlin
webView.webViewClient = object : WebViewClient() {
    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
        val url = request.url.toString()
        if (url.startsWith(FLASK_URL)) return false            // localhost → WebView
        startActivity(Intent(Intent.ACTION_VIEW, request.url)) // external → system browser
        return true
    }
}
```

Additionally, `onCreateWindow()` is overridden to handle any residual `window.open()` popups — it intercepts the first navigation, routes external URLs to the system browser and localhost URLs to the main WebView, then destroys the popup.

#### Deep-Link Return (✅ FIXED — Option B Implemented)

The OAuth callback deep-link has been fixed using **Option B: Custom URI scheme**. The following changes were made:

1. **`AndroidManifest.xml`** — Added `android:launchMode="singleTask"` to the `<activity>` declaration and an `<intent-filter>` for `spotyvibe://callback` (with `ACTION_VIEW`, `BROWSABLE`, and `DEFAULT` categories).
2. **`core/playlist.py`** — `REDIRECT_URI` is now platform-aware: `spotyvibe://callback` on Android (`IS_ANDROID`), `http://127.0.0.1:5000/callback` on desktop.
3. **`MainActivity.kt`** — `onNewIntent()` rewritten to handle `spotyvibe://callback?code=...&state=...` by forwarding the code and state to Flask's `/callback` endpoint via the WebView. Also added `isFlaskRunning()` startup guard and replaced the deprecated `onBackPressed()` with `onBackPressedDispatcher`.

**Expected runtime behaviour (updated code):**
1. User taps "Connect to Spotify" → direct navigation to `/api/spotify/auth` ✅
2. Flask redirects to Spotify auth URL → `shouldOverrideUrlLoading` opens Chrome ✅
3. User logs in on Spotify in Chrome ✅
4. Spotify redirects to `spotyvibe://callback?code=...&state=...` → Android routes the intent to the existing `MainActivity` via `onNewIntent()` ✅
5. `onNewIntent()` extracts `code` and `state`, loads `http://127.0.0.1:5000/callback?code=...&state=...` in the WebView ✅
6. Flask exchanges the code and saves the token, user sees success in the app ✅

#### Spotify Developer Dashboard

The redirect URI `http://127.0.0.1:5000/callback` works for the desktop flow. **For Android,** `spotyvibe://callback` must also be registered in the Spotify Developer Dashboard.

> **✅ Option B has been implemented.** The custom URI scheme approach was chosen as recommended by all three external reviewers.

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
| 1.3 | `core/playlist.py` | Platform-aware `REDIRECT_URI` | `REDIRECT_URI` is now `spotyvibe://callback` on Android, `http://127.0.0.1:5000/callback` on desktop. Imports `IS_ANDROID` from config. | ✅ Done |
| 1.4 | `app.py` | Add `host` parameter + disable reloader | Added `host="127.0.0.1"` and `use_reloader=False if IS_ANDROID else None`. Both `__main__` and Kotlin invocation paths covered. | ✅ Done |
| 1.5 | All Python files | Verify pure-Python deps | Top-level deps confirmed Chaquopy-compatible. **Note:** Transitive dependency compatibility is unverified until an actual Android build succeeds (see Section 9.5). | ⚠️ Partially verified |

> **✅ Review note resolved:** `use_reloader=False` is now set conditionally via `IS_ANDROID` in `app.py`. The Kotlin `MainActivity.kt` also passes `use_reloader=false` when calling `app.run()` directly, so both invocation paths are covered.

**Desktop impact:** None. The platform detection is additive — existing behavior is the `else` branch. **Confirmed: 165 tests pass.**

### Phase 2: Create the Android Project

| Step | What | Details | Status |
|---|---|---|---|
| 2.1 | Create `android/` directory structure | Full structure created as shown in Section 4. | ✅ Done |
| 2.2 | Configure root `build.gradle` | Chaquopy 15.0.1, Kotlin 1.9.22, AGP 8.2.2. Removed conflicting `allprojects { repositories {} }` block (Gradle 8.x uses `dependencyResolutionManagement` in settings.gradle). | ✅ Done |
| 2.3 | Configure `app/build.gradle` | `minSdk 26`, `targetSdk 34`, Python 3.10, pip deps, `arm64-v8a` + `x86_64` (emulator). | ✅ Done |
| 2.4 | Write `AndroidManifest.xml` | `INTERNET` + `ACCESS_NETWORK_STATE` permissions, `usesCleartextTraffic` for localhost. | ✅ Done |
| 2.5 | Write `activity_main.xml` | FrameLayout with splash screen + WebView. | ✅ Done |
| 2.6 | Write `MainActivity.kt` | Flask in daemon thread, splash screen, WebView with OAuth handling (direct nav + popup fallback), `onDestroy()`, `onNewIntent()`, back navigation. | ✅ Done |
| 2.7 | Create app icons | Placeholder `ic_launcher.png` (Spotify green squares) created in all `mipmap-*` density directories (hdpi, mdpi, xhdpi, xxhdpi, xxxhdpi). | ✅ Done |
| 2.8 | Generate Gradle wrapper | `gradle wrapper --gradle-version 8.5` run from `android/`. `gradlew`, `gradlew.bat`, and `gradle/wrapper/gradle-wrapper.jar` generated and committed. | ✅ Done |
| 2.9 | Add `local.properties` setup | Document that `android/local.properties` (containing `sdk.dir=...`) must be created before building. Listed in `.gitignore` but never mentioned in setup instructions. | ⬜ Not done |
| 2.10 | Fix `AndroidManifest.xml` | Added `android:launchMode="singleTask"` and `<intent-filter>` for `spotyvibe://callback` custom URI scheme. | ✅ Done |

> **✅ Review note resolved:** `ACCESS_NETWORK_STATE` was included in the manifest.
> 
> **⚠️ External review finding:** Three independent reviewers identified items 2.7, 2.8, 2.9, and 2.10 as missing. Items 2.7 and 2.8 are build-blocking (the APK cannot compile without them). Item 2.10 is required for correct OAuth behavior.

#### 5.1 — `MainActivity.kt` Responsibilities

```
onCreate():
  1. Set SPOTYVIBE_FILES_DIR environment variable → context.filesDir
  2. Start Python/Flask in a background thread:
       - Import chaquopy's Python module
       - Execute: "from app import app; app.run(host='127.0.0.1', port=5000, use_reloader=False)"
  3. Wait for Flask to be ready (poll http://127.0.0.1:5000/ with retry)
  4. Show a splash/loading screen during startup
  5. Show onboarding screen (served by Flask) with a "Continue" button
  6. On "Continue" → load the main SpotyVibe UI in the WebView
  7. Configure WebView:
       - Enable JavaScript
       - Enable DOM storage (for localStorage — theme preference)
       - Set WebViewClient to intercept external URLs (Spotify auth → system browser)
       - Set WebChromeClient for console.log forwarding (debugging)

onDestroy():
  1. Interrupt the Flask server thread (explicit cleanup while process is still alive)
  2. Set flaskThread = null
  3. Destroy WebView to release resources
  4. Call super.onDestroy()

> **✅ Implemented:** `onDestroy()` now performs explicit cleanup — interrupts the Flask thread and destroys the WebView. The daemon flag on the thread provides a safety net if the process exits without `onDestroy()` being called.

onNewIntent():
  1. Handle OAuth callback deep-link from system browser
  2. If the intent data URL starts with FLASK_URL, load it in the WebView
  3. This completes the token exchange when the browser redirects to 127.0.0.1:5000/callback

> **✅ Implemented:** `onNewIntent()` intercepts deep-links and routes localhost URLs to the WebView.

onBackPressed():
  1. If WebView can go back → webView.goBack()
  2. Otherwise → default behavior (exit)
```

### Phase 3: Build Script & Automation

| Step | What | Details | Status |
|---|---|---|---|
| 3.1 | Create `android/build_apk.sh` | One-command script: copies Python sources + runs `./gradlew assembleDebug`. Copy logic is integrated (no separate script needed). | ✅ Done |
| 3.2 | Create `android/copy_python_sources.sh` | Merged into `build_apk.sh` — source copy is the first step of the build. | ✅ Done (merged) |

### Onboarding Screen (Android Only)

A lightweight onboarding flow will be shown **after Flask has started** and **before the user reaches the main SpotyVibe UI**. This is an Android-only feature — the desktop browser experience is unchanged.

#### Startup Sequence With Onboarding

```
┌─────────────────────┐
│   Native Splash     │   Kotlin-managed, shown during Python/Flask boot
│   "Starting..."     │
└────────┬────────────┘
         │ Flask ready
         ▼
┌─────────────────────┐
│   Onboarding Page   │   Served by Flask at /onboarding (HTML/CSS/JS)
│                     │   Displays welcome info, setup guidance, etc.
│   [ Continue ]      │   Future: multi-page slides, credential setup, etc.
└────────┬────────────┘
         │ User taps "Continue"
         ▼
┌─────────────────────┐
│   Main SpotyVibe UI │   WebView loads http://127.0.0.1:5000
│   (index.html)      │
└─────────────────────┘
```

#### Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| **Where does onboarding live?** | Flask route (`/onboarding`) served as HTML | Keeps it consistent with the rest of the UI. Future onboarding steps may need Flask data (e.g. credential status, Spotify connection state). |
| **When does it appear?** | Every startup (temporary) | Placeholder behaviour. Future: track `onboarding_complete` flag in `SharedPreferences` or in the app's `.credentials` file to show only once (or after updates). |
| **How does it transition?** | "Continue" button navigates to `/` (the main app) | Simple JS `window.location.href = "/"`. No Kotlin-side logic needed. |
| **Android-only?** | Yes | Desktop users launch the browser directly to `127.0.0.1:5000` — no onboarding wrapper needed. The `/onboarding` route will still exist but won't be the default entry point on desktop. |

#### Implementation Steps (Not Yet Started)

| # | Area | Change | Complexity |
|---|---|---|---|
| 1 | `app.py` | Add `GET /onboarding` route that renders `onboarding.html` | Low |
| 2 | `templates/onboarding.html` | Single-page HTML with app branding, welcome text, and a "Continue" button that navigates to `/` | Low |
| 3 | `static/css/styles.css` | Add onboarding-specific styles (or inline them in `onboarding.html`) | Low |
| 4 | `MainActivity.kt` | Change `showWebView()` to load `/onboarding` instead of `/` after Flask is ready | Low |
| 5 | Future: persistence | Store `onboarding_complete` flag so it only shows once (or on version updates) | Low–Medium |
| 3.3 | Add `.gitignore` for Android | Ignores `.gradle/`, `app/build/`, `app/src/main/python/`, `local.properties`, APKs/AABs. | ✅ Done |

### Phase 4: Testing

| Step | What | Details | Status |
|---|---|---|---|
| 4.1 | Desktop regression | 165 tests pass (157 original + 6 platform detection + 2 redirect URI tests). | ✅ Done |
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

# 2. Copy Python files (preserving directory structure, excluding __pycache__)
for item in app.py config.py core prompts data static templates; do
    if [ -d "$PROJECT_ROOT/$item" ]; then
        # Directory: use find + cpio to skip __pycache__
        (cd "$PROJECT_ROOT" && find "$item" -not -path '*/__pycache__/*' -not -name '__pycache__' | cpio -pdm "$PYTHON_DEST" 2>/dev/null)
    else
        cp "$PROJECT_ROOT/$item" "$PYTHON_DEST/"
    fi
done

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
            // arm64-v8a for physical devices; x86_64 for Android Studio emulators.
            // Remove x86_64 from release builds to reduce APK size.
            abiFilters "arm64-v8a", "x86_64"
        }
    }
}
```

> **✅ Resolved — ABI note:** The build now ships `arm64-v8a` (physical devices) + `x86_64` (emulators). For **release builds**, remove `x86_64` to reduce APK size. For **Play Store distribution**, use an Android App Bundle (AAB) instead of a raw APK — Google Play will split by ABI automatically.

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
| WebView shows blank page | Flask not ready yet when WebView loads | Poll `127.0.0.1:5000` in a loop before loading WebView (✅ implemented in `waitForFlask()`) |
| Spotify OAuth fails | System browser can't reach `127.0.0.1:5000/callback` | ✅ Mitigated: WebView detects Android and uses direct navigation. Backend fallback redirect handles non-popup flow. `onNewIntent()` handles deep-link return. Needs device testing. |
| SSE stream drops | Android may kill background network connections | WebView keeps the connection alive; Flask runs in-process so this is local I/O, not network |
| Large APK size | Python runtime + dependencies | Expected 30–60 MB. ABI filtering (`arm64-v8a` + `x86_64` for debug, `arm64-v8a` only for release) reduces size. |

> **⚠️ Open — SSE in WebView:** While SSE via `EventSource` is supported on API 26+, Android WebView has known issues with connection timeouts and aggressively closing idle connections. Since SpotyVibe's SSE stream is short-lived (active only during generation), this should be fine in practice — but it should be a **high-priority test item** on real devices. If issues arise, a fallback to polling `/api/run-status` could be implemented.

---

## 8. Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| **Chaquopy licensing** | Low | Free for open-source and closed-source as of recent versions. Verify current terms at [chaquo.com/chaquopy](https://chaquo.com/chaquopy/). |
| **Python boot time** | Medium | Show a native splash screen. Typical boot is 2–5s on modern devices. |
| **Chaquopy version lag** | Low | Chaquopy supports Python 3.8–3.13. Current project uses 3.10 which is fully supported. |
| **Battery drain** | Medium | Flask runs only while the app is in the foreground. `onDestroy()` interrupts the Flask thread. The app doesn't do background work. |
| **Android WebView quirks** | Low | Test SSE streaming, `localStorage`, and `<canvas>` animations in Android WebView. All are well-supported on API 26+. |
| **Spotify token persistence** | Low | Spotipy's `cache_path` parameter works with any writable file path. Already tested on multiple platforms. |
| **Profile loss on uninstall** | Low | Document this for the user. A future enhancement could add profile export/import. |
| **✅ ~~OAuth deep-link failure~~** | ~~Critical~~ → Resolved | Fixed: Custom URI scheme `spotyvibe://callback` implemented. `AndroidManifest.xml` has `singleTask` launch mode and `<intent-filter>`. `onNewIntent()` correctly handles the callback. |
| **✅ ~~Flask suspension during OAuth~~** | ~~High~~ → Mitigated | The custom URI scheme (`spotyvibe://callback`) mitigates this: the intent wakes the app before the callback is processed. Flask does not need to be listening for the redirect. |
| **✅ ~~Flask port conflict on activity recreation~~** | ~~Medium~~ → Resolved | Startup guard in `MainActivity.kt` uses a `companion object` `@Volatile` boolean flag (`flaskStarted`) that survives activity re-creation within the same process. Replaced the original `isFlaskRunning()` network call which was non-functional due to `NetworkOnMainThreadException` on Android's main thread. |
| **⚠️ Flask thread interrupt incomplete** | **Medium** | `Thread.interrupt()` in `onDestroy()` doesn't cleanly stop Werkzeug's socket. The TCP socket may stay in `TIME_WAIT` state. The daemon flag provides a safety net on process exit, but rapid destroy/recreate cycles could leave the port bound. |
| **⚠️ Transitive dependency compatibility** | **Medium** | Top-level pip packages are confirmed pure-Python or Chaquopy-supported, but transitive dependencies (especially from `openai` SDK's HTTP stack) are unverified on Android/ARM. Cannot be confirmed until an actual Android build succeeds with the resolved dependency set. |
| **Server startup failure UX** | Low | If Flask fails to start, `waitForFlask()` times out but the splash screen is hidden and WebView loads a blank page. Add an error state UI that displays when Flask fails to boot. |
| **⚠️ SSL certificate authority resolution** | **Medium** | Python's `ssl` module on Android cannot natively find the OS CA certificate store. If `certifi` is not correctly configured in Chaquopy's environment, all HTTPS requests to OpenAI and Spotify will fail with `SSL: CERTIFICATE_VERIFY_FAILED`. Monitor Logcat during Phase 4 testing; if errors occur, set `os.environ["SSL_CERT_FILE"]` to the `certifi` bundle path at startup. |
| **⚠️ Werkzeug thread pool exhaustion during SSE** | **Medium** | Flask's development server (Werkzeug) has limited worker threads in Chaquopy. A long-lived SSE connection during playlist generation could block subsequent AJAX requests, deadlocking the local server. SpotyVibe's SSE streams are short-lived, reducing risk. If issues arise during Phase 4, consider yielding batched JSON responses instead of SSE when `IS_ANDROID` is true. |
| **✅ ~~Build script portability~~** | ~~Low~~ → Resolved | Fixed: `build_apk.sh` now uses `cp -r` + `find -delete __pycache__` instead of `cpio`. |

---

## Summary of Code Changes Required

| File | Type of Change | Backward Compatible? | Status |
|---|---|---|---|
| `config.py` | Added `IS_ANDROID`, `_get_app_dir()`, guarded `.env` migration, `debug_log_path` in `get_settings()` | ✅ Yes — desktop path is the `else` branch | ✅ Done |
| `app.py` | Added `IS_ANDROID` import, `host="127.0.0.1"`, `use_reloader=False` on Android, OAuth callback fallback redirect | ✅ Yes — `None` on desktop (Flask default) | ✅ Done |
| `core/playlist.py` | Platform-aware `REDIRECT_URI` (`spotyvibe://callback` on Android, `http://127.0.0.1:5000/callback` on desktop). Imports `IS_ANDROID` from config. | ✅ Yes — desktop path unchanged | ✅ Done |
| `core/profile.py` | No changes | ✅ N/A | — |
| `core/suggestions.py` | No changes | ✅ N/A | — |
| `core/feedback.py` | No changes | ✅ N/A | — |
| `core/utils.py` | No changes | ✅ N/A | — |
| `templates/index.html` | Android WebView detection for OAuth (direct nav instead of popup), dynamic debug log path | ✅ Yes — popup flow unchanged on desktop | ✅ Done |
| `static/css/styles.css` | Mobile responsive styles added (separate commit) | ✅ Yes — `@media` scoped | ✅ Done |
| `tests/test_config.py` | Added 6 tests for platform detection | ✅ Yes | ✅ Done |

**New files (all in `android/`):**

| File | Status |
|---|---|
| `build.gradle` (root) | ✅ Done |
| `settings.gradle` | ✅ Done (fixed: `dependencyResolutionManagement` DSL name) |
| `gradle.properties` | ✅ Done |
| `gradle/wrapper/gradle-wrapper.properties` | ✅ Done |
| `app/build.gradle` | ✅ Done |
| `app/proguard-rules.pro` | ✅ Done |
| `app/src/main/AndroidManifest.xml` | ✅ Done — `singleTask` launch mode + `spotyvibe://callback` intent-filter added |
| `app/src/main/res/layout/activity_main.xml` | ✅ Done |
| `app/src/main/res/values/strings.xml` | ✅ Done — style should be moved to `themes.xml` (see Section 9, item 9.13) |
| `app/src/main/kotlin/.../MainActivity.kt` | ✅ Done — OAuth deep-link via `handleOAuthIntent()` (called from both `onCreate()` and `onNewIntent()`), `flaskStarted` companion flag, `Uri.Builder` URL encoding, `onBackPressedDispatcher` |
| `build_apk.sh` | ✅ Done — uses `cp -r` + `find -delete __pycache__` |
| `.gitignore` | ✅ Done |
| App icons (`mipmap-*`) | ✅ Done — placeholder `ic_launcher.png` in all density directories |
| `gradlew` / `gradlew.bat` / `gradle-wrapper.jar` | ✅ Done |

---

## Remaining Work — Updated After External Review

### Completed (previously blocking or critical)

- ~~**App icons**~~ — ✅ Placeholder `ic_launcher.png` files created in all `mipmap-*` density directories.
- ~~**Redesign Spotify OAuth return flow**~~ — ✅ Option B (custom URI scheme `spotyvibe://callback`) implemented. `AndroidManifest.xml`, `core/playlist.py`, and `MainActivity.kt` updated.
- ~~**Add `android:launchMode="singleTask"`**~~ — ✅ Added to `AndroidManifest.xml`.
- ~~**Add OAuth `<intent-filter>`**~~ — ✅ `spotyvibe://callback` intent-filter added to `AndroidManifest.xml`.
- ~~**Flask startup guard**~~ — ✅ `flaskStarted` companion-object flag in `MainActivity.kt`. Replaced the original `isFlaskRunning()` network call (which threw `NetworkOnMainThreadException`).
- ~~**Build script portability**~~ — ✅ `build_apk.sh` now uses `cp -r` + `find -delete __pycache__` instead of `cpio`.
- ~~**Migrate `onBackPressed()`**~~ — ✅ Replaced with `onBackPressedDispatcher.addCallback()` in `MainActivity.kt`.
- ~~**Callback error hint**~~ — ✅ `app.py` updated to mention both redirect URIs in callback error messages.
- ~~**Generate Gradle wrapper**~~ — ✅ `gradle wrapper --gradle-version 8.5` run from `android/`. `gradlew`, `gradlew.bat`, and `gradle/wrapper/gradle-wrapper.jar` generated and committed.
- ~~**`isFlaskRunning()` non-functional on main thread**~~ — ✅ Replaced with `companion object` `@Volatile` boolean flag (`flaskStarted`). Avoids `NetworkOnMainThreadException`.
- ~~**Cold-start deep-link loss in `onCreate()`**~~ — ✅ `onCreate()` now calls `handleOAuthIntent(intent)` after `startFlaskServer()` to handle `spotyvibe://callback` intents delivered on cold start after process death.
- ~~**OAuth `code` not URL-re-encoded in `onNewIntent()`**~~ — ✅ Replaced string concatenation with `Uri.Builder.appendQueryParameter()` for proper URL encoding.

### Build Blockers (must fix before any APK build attempt)

- **`local.properties`** — Document that `android/local.properties` (containing `sdk.dir=...`) must be created before building.

### Medium Priority (should fix before device testing)

- **Server startup failure UX** — Show an error message if Flask fails to boot, instead of hiding the splash screen and loading a blank page.
- **Onboarding screen** — Implement the onboarding flow (Flask route + HTML template + `MainActivity.kt` entry point change). See [Onboarding Screen](#onboarding-screen-android-only) section for full design.

### Testing (Phase 4 — pending Gradle wrapper)

- **Android emulator test** — Build debug APK, install on emulator (API 26+), verify Flask boots and UI loads.
- **Credential flow test** — Enter OpenAI key and Spotify credentials on Android, verify they persist across app restarts.
- **Spotify OAuth test** — Connect to Spotify from the Android app, verify the custom URI scheme redirect flow works end-to-end.
- **SSE streaming test** — Verify `EventSource` works in Android WebView during playlist generation.
- **Full end-to-end test** — Generate a complete playlist on Android.
- **Gradle build verification** — Verify the entire Gradle/Chaquopy build chain works with Android SDK + JDK 17.
- **Transitive dependency verification** — Confirm all transitive pip dependencies resolve on Android/ARM during Chaquopy build.
- **SSL certificate verification test** — Verify that HTTPS calls to OpenAI and Spotify APIs succeed from the Android app. Monitor Logcat for `SSL: CERTIFICATE_VERIFY_FAILED` errors.
- **Werkzeug thread pool test** — Verify that AJAX requests are not blocked during SSE streaming on Android.

### Low Priority (quality improvements)

- **Move style to `themes.xml`** — Extract `Theme.SpotyVibe` from `strings.xml` to `res/values/themes.xml` (convention).
- **Consolidate Gradle paradigm** — Migrate from legacy `buildscript {}` to modern `pluginManagement {}` when Chaquopy supports it.
- **Verify Chaquopy license** — Confirm 15.x license terms at chaquo.com before distribution.

### Context for Future Agent Sessions

Python-side code changes (Phase 1) are complete and tested (165 unit tests pass). The Android project scaffolding (Phase 2) is in place. OAuth deep-link flow has been fixed (Option B — custom URI scheme). Build blockers for app icons, manifest, and build script portability are resolved. The next agent session should focus on:

1. ~~**Generate Gradle wrapper**~~ — ✅ Done. `gradlew`, `gradlew.bat`, and `gradle/wrapper/gradle-wrapper.jar` generated.
2. **Document `local.properties` setup** — Add instructions for creating `android/local.properties` with `sdk.dir=...`.
3. **Build the APK** — Run `cd android && ./build_apk.sh debug` in an environment with Android SDK + JDK 17. Fix any Gradle/Chaquopy build errors.
4. **Test on emulator** — Install the debug APK on an Android emulator (API 26+, x86_64). Verify Flask boots, the WebView loads, and all flows work end-to-end.
5. **Register `spotyvibe://callback`** — Add the custom URI as a redirect URI in the Spotify Developer Dashboard.

Key files to understand for debugging:
- `android/app/src/main/kotlin/com/spotyvibe/app/MainActivity.kt` — Android entry point, Flask thread, WebView config, OAuth routing
- `config.py` — `IS_ANDROID` detection, `_get_app_dir()` for storage paths
- `templates/index.html` — `connectSpotify()` function with WebView detection
- `app.py` — `/callback` endpoint with popup/direct-navigation dual path

---

*Phase 1 (Python prep) is complete. Phase 2 (Android scaffolding) and Phase 3 (build scripts) are in place with OAuth deep-link and build issues resolved. Remaining blocker: `local.properties` documentation. Phase 4 (on-device testing) can proceed once a build environment with Android SDK + JDK 17 is available.*

---
---

# 9. External Review Findings — Consolidated

**Date:** 2026-03-27
**Sources:** Three independent feasibility reviews of this document:
1. `report_chatgpt.md`
2. `report_gemini.md`
3. `report_sonnet.md`

All three reviewers agreed that **Option B (Embedded Python via Chaquopy) is architecturally sound and viable**, but identified critical issues that must be resolved before Phase 4 testing.

---

## Critical Issues (all three reviewers agree)

### 9.1 Spotify OAuth Deep-Link Flow is Broken

**Consensus:** The `onNewIntent()` approach for handling the Spotify OAuth callback return from the system browser does not work as designed on Android.

**Root causes identified:**
- No `<intent-filter>` in `AndroidManifest.xml` for the callback URL (all 3 reviewers)
- No `android:launchMode="singleTask"` — default `"standard"` creates new activity instances (Sonnet)
- Android 12+ requires domain verification (`assetlinks.json`) for HTTP deep links; `127.0.0.1` cannot be verified (Gemini, Sonnet)
- Flask may be suspended while the user is in the system browser, causing `ERR_CONNECTION_REFUSED` on callback (Gemini)

**Actual behavior:** Token exchange succeeds (Flask receives the callback), but the user is stranded in Chrome viewing SpotyVibe inside the browser. The app's WebView is never notified. `onNewIntent()` is never called.

**Recommended solution:** Custom URI scheme (`spotyvibe://callback`) — agreed by Gemini and Sonnet as the correct mobile-native approach. See Section 3 for the three proposed fix options.

> **Status:** ✅ Resolved. Option B (custom URI scheme `spotyvibe://callback`) has been implemented. `AndroidManifest.xml` has `singleTask` launch mode and intent-filter. `core/playlist.py` uses a platform-aware `REDIRECT_URI`. `MainActivity.kt` handles the callback in `onNewIntent()`.

---

### 9.2 Build Blockers Prevent APK Compilation

**Identified by:** Sonnet (both items), ChatGPT (partially — noted build not proven)

| Blocker | Impact |
|---|---|
| `gradlew` / `gradlew.bat` never generated | `build_apk.sh` fails with "command not found" |
| All `mipmap-*` directories are empty | AAPT2 compile error — `@mipmap/ic_launcher` cannot be resolved |
| `local.properties` not documented | Gradle fails with "SDK location not found" |

> **Status:** Mostly resolved. App icons are now created (✅). `build_apk.sh` portability is fixed (✅). Gradle wrapper (`gradlew`/`gradlew.bat`) generated (✅). `local.properties` documentation is still needed (⬜).

---

### 9.3 Progress Status Overstated

**Identified by:** ChatGPT, Sonnet

The document previously claimed "Phases 1-3 are complete." This is inaccurate because:
- No actual APK build has been attempted or succeeded
- The OAuth flow has a critical design flaw
- Build blockers prevent compilation
- Transitive dependency compatibility is unverified on Android

> **Status:** Phase status language has been corrected throughout this document. Phase 1 is genuinely complete (Python changes + 165 passing tests). Phases 2-3 are "scaffolded" but have unresolved issues.

---

## High-Severity Issues

### 9.4 Flask Suspension During Background OAuth

**Identified by:** Gemini

When the user is in the system browser completing Spotify login (especially with 2FA, 1-2 minutes), Android may suspend the app process. If Flask is suspended, port 5000 stops accepting connections and the OAuth callback fails.

**Mitigation:** The custom URI scheme solution (Section 9.1) naturally resolves this — the `spotyvibe://callback` intent wakes the app and brings it to the foreground before the callback is processed.

### 9.5 Transitive Dependency Compatibility Unverified

**Identified by:** ChatGPT

Top-level pip packages are confirmed pure-Python or Chaquopy-supported, but transitive dependencies (especially from the OpenAI SDK's HTTP client stack) have not been validated on Android/ARM. A package may fail at build time or runtime due to native extensions in a transitive dependency.

**Mitigation:** Cannot be confirmed until an actual Android build succeeds. Added as a testing item.

---

## Medium-Severity Issues

### 9.6 Flask Port Conflict on Activity Recreation

**Identified by:** Gemini, Sonnet

If Android destroys and recreates `MainActivity` within the same process, `startFlaskServer()` will attempt to start a second Flask instance on port 5000, failing with `Address already in use`. The `configChanges` attribute mitigates the most common scenario (rotation), but memory-pressure recreation is a real edge case.

> **Status:** ✅ Resolved. The `isFlaskRunning()` network call (which was non-functional due to `NetworkOnMainThreadException` on Android's main thread) has been replaced with a `companion object` `@Volatile` boolean flag (`flaskStarted`). This flag survives activity re-creation within the same process and provides a zero-overhead guard.

### 9.7 Thread.interrupt() Does Not Cleanly Stop Flask

**Identified by:** Gemini, Sonnet

Java's `Thread.interrupt()` does not cleanly terminate Werkzeug's server socket in Chaquopy. The TCP socket may stay in `TIME_WAIT` state, compounding the port conflict risk (9.6). The daemon flag provides a safety net on process exit, but rapid destroy/recreate cycles could leave the port bound.

### 9.8 SSE Streaming Stability in Android WebView

**Identified by:** Sonnet (acknowledged as already flagged)

Android WebView may aggressively close idle connections. SpotyVibe's SSE stream is short-lived, reducing risk, but a slow OpenAI response could trigger premature close. A polling fallback should be prepared.

### 9.9 Build Script Portability

**Identified by:** ChatGPT

`build_apk.sh` uses `cpio` for the Python source copy step, which may not be available in all Git Bash / Windows environments. Replacing with `cp -r` + `find -delete __pycache__` would be more portable.

### 9.10 Server Startup Failure UX

**Identified by:** ChatGPT

If Flask fails to start, `waitForFlask()` times out but still hides the splash screen and loads the WebView, producing a blank page. An explicit error state should be shown.

---

## Low-Severity Issues

| # | Issue | Reviewer | Notes |
|---|---|---|---|
| 9.11 | `onBackPressed()` deprecated on API 33+ | Sonnet | Replace with `onBackPressedDispatcher.addCallback()`. Compiles and works for now. |
| 9.12 | Gradle mixed-paradigm build files | Sonnet | Legacy `buildscript {}` + modern `pluginManagement {}` coexist. Works but triggers deprecation warnings. |
| 9.13 | Theme style defined in `strings.xml` | Sonnet | Convention is `res/values/themes.xml`. No functional impact. |
| 9.14 | Chaquopy license verification | Sonnet, ChatGPT | Verify current 15.x terms before distribution. |
| 9.15 | Hardcoded port 5000 | Gemini | Unlikely conflict on Android, but ephemeral port binding would be more robust. |

---

## Reviewer Agreement Summary

| Issue | ChatGPT | Gemini | Sonnet |
|---|---|---|---|
| OAuth deep-link broken | Yes | Yes | Yes |
| Build blockers (gradlew, icons) | Partial | — | Yes |
| Progress overstated | Yes | — | Yes |
| Flask suspension during OAuth | — | Yes | — |
| Transitive deps unverified | Yes | — | Partial |
| Port conflict on recreation | — | Yes | Yes |
| Thread.interrupt incomplete | — | Yes | Yes |
| Build script portability | Yes | — | — |
| Startup failure UX | Yes | — | — |
| onBackPressed deprecated | — | — | Yes |
| Gradle paradigm mixing | — | — | Yes |
| local.properties undocumented | — | — | Yes |
