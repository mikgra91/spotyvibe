# Learning Guide: SpotyVibe — Android APK Edition

This document explains **how** SpotyVibe is packaged as a native Android APK, **what** technologies make it work, and **why** each architectural decision was made. It is written for developers who want to understand the hybrid Python-on-Android architecture end-to-end — from Gradle build configuration through Kotlin lifecycle management to the embedded Flask server.

For the Python backend and frontend technologies, see [learning-windows.md](learning-windows.md). This guide focuses on the Android-specific layer that wraps the same codebase into a mobile app.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Key Technologies](#key-technologies)
   - [Chaquopy — Embedded Python for Android](#chaquopy--embedded-python-for-android)
   - [Android WebView](#android-webview)
   - [Custom URI Schemes & Deep Linking](#custom-uri-schemes--deep-linking)
   - [Server-Sent Events in WebView](#server-sent-events-in-webview)
3. [Gradle Build Configuration](#gradle-build-configuration)
   - [Plugin Stack](#plugin-stack)
   - [Android SDK Configuration](#android-sdk-configuration)
   - [Chaquopy Python Configuration](#chaquopy-python-configuration)
   - [NDK Architecture Filters](#ndk-architecture-filters)
   - [Dependencies](#dependencies)
   - [ProGuard](#proguard)
4. [Android Manifest & Intents](#android-manifest--intents)
   - [Permissions](#permissions)
   - [Application Configuration](#application-configuration)
   - [Activity Configuration](#activity-configuration)
   - [Intent Filters](#intent-filters)
5. [Resources & Styling](#resources--styling)
   - [Theme Configuration](#theme-configuration)
   - [Layout — Three-Layer View Stack](#layout--three-layer-view-stack)
6. [Kotlin Implementation — MainActivity](#kotlin-implementation--mainactivity)
   - [Flask Server Lifecycle](#flask-server-lifecycle)
   - [WebView Configuration & Security](#webview-configuration--security)
   - [WebViewClient — URL Routing](#webviewclient--url-routing)
   - [WebChromeClient — File Chooser & Popups](#webchromeclient--file-chooser--popups)
   - [Download Management & Security](#download-management--security)
   - [OAuth Deep-Link Handling](#oauth-deep-link-handling)
   - [Profile Import via Share Intent](#profile-import-via-share-intent)
   - [Back Press Handling](#back-press-handling)
   - [Activity Lifecycle](#activity-lifecycle)
7. [Python Bootstrapping](#python-bootstrapping)
   - [spotyvibe_bootstrap.py](#spotyvibe_bootstrappy)
   - [config.py — Android-Specific Paths](#configpy--android-specific-paths)
8. [Android Onboarding Flow](#android-onboarding-flow)
9. [OAuth Flow on Android](#oauth-flow-on-android)
10. [Chaquopy Constraints & Dependency Strategy](#chaquopy-constraints--dependency-strategy)
11. [Build Script & APK Packaging](#build-script--apk-packaging)
12. [Security Architecture](#security-architecture)
13. [General Use Cases for This Architecture](#general-use-cases-for-this-architecture)
14. [Potential Pitfalls](#potential-pitfalls)
15. [Documentation & Learning Resources](#documentation--learning-resources)

---

## Architecture Overview

The SpotyVibe Android app uses a **hybrid local-server architecture**. Instead of rewriting the Python backend into Kotlin/Java or hosting it on a cloud server, the entire Python runtime is embedded inside the Android app.

```
┌─────────────────────────────────────────────┐
│            Android App (APK)                │
│                                             │
│  ┌────────────────────────────────────────┐ │
│  │   Native Shell (Kotlin)                │ │
│  │   MainActivity.kt                      │ │
│  │   - Flask lifecycle (start/wait/error) │ │
│  │   - WebView configuration & security   │ │
│  │   - OAuth deep-link handling           │ │
│  │   - Share intent for profile import    │ │
│  │   - Download restrictions              │ │
│  │   - Back-press navigation              │ │
│  └─────────────┬──────────────────────────┘ │
│                │                             │
│  ┌─────────────▼──────────────────────────┐ │
│  │   WebView (embedded browser)           │ │
│  │   Renders Flask HTML/CSS/JS at         │ │
│  │   http://127.0.0.1:5000               │ │
│  │   - JavaScript enabled                 │ │
│  │   - DOM storage (localStorage)         │ │
│  │   - SSE streaming support              │ │
│  │   - File chooser for profile import    │ │
│  └─────────────┬──────────────────────────┘ │
│                │ HTTP (localhost)             │
│  ┌─────────────▼──────────────────────────┐ │
│  │   Flask Server (Python via Chaquopy)   │ │
│  │   Same codebase as desktop             │ │
│  │   - app.py, core/*, frontend/*         │ │
│  │   - Data stored in internal storage    │ │
│  │   - No OpenAI SDK (direct HTTP)        │ │
│  └────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

**Three layers:**
1. **Native Shell (Kotlin):** A minimal Android Activity that manages the lifecycle, handles deep links (OAuth), processes share intents (profile import), and enforces security restrictions.
2. **Local Backend (Chaquopy + Python):** A background thread running the Flask server on `127.0.0.1:5000`. Uses the exact same Python code as the desktop version.
3. **Frontend (WebView):** An embedded Chromium-based browser pointed at the local Flask server. Renders the same HTML/CSS/JS as a desktop browser.

**Pinned build versions for reproducibility:**

| Component | Version |
|---|---|
| Android Gradle Plugin | 8.2.2 |
| Kotlin | 1.9.22 |
| Chaquopy | 15.0.1 |
| Gradle | 8.5 |
| Compile/Target SDK | 34 (Android 14) |
| Min SDK | 26 (Android 8.0) |
| Java | 17 |
| Python | 3.10 |

---

## Key Technologies

### Chaquopy — Embedded Python for Android

[Chaquopy](https://chaquo.com/chaquopy/) is a Gradle plugin that embeds CPython into an Android app.

**How it works:**
- At build time, the plugin bundles the Python 3.10 interpreter and specified pip packages into the APK.
- At runtime, Kotlin/Java code starts the interpreter and calls Python functions via `com.chaquo.python.Python`.
- Python code runs in the app's process — no separate server or container.

**Why it was used:**
- The SpotyVibe backend relies heavily on Python packages (`flask`, `spotipy`, `python-dotenv`) and custom Python logic (GPT prompt engineering, dedup algorithms).
- Rewriting this in Kotlin would be expensive, error-prone, and would duplicate business logic.
- Chaquopy allows the same Python code to run unmodified on both desktop and Android.
- All data stays on-device — no cloud server needed.

**Constraints:**
- Only pure-Python or pre-compiled C-extension packages work. Rust-compiled extensions (like `jiter`, `pydantic-core`) cannot be built.
- This is why the OpenAI SDK was replaced with a custom `urllib`-based HTTP client — see [Chaquopy Constraints](#chaquopy-constraints--dependency-strategy).

### Android WebView

[Android WebView](https://developer.android.com/develop/ui/views/layout/webapps/webview) is a system component that displays web content inside an Android app.

**How it works:**
- Acts as an embedded Chromium browser.
- Points to `http://127.0.0.1:5000` — the local Flask server.
- Supports JavaScript, DOM storage (localStorage), SSE streaming, file choosers, and popup windows.

**Key configuration required:**
- `javaScriptEnabled = true` — required for the SPA frontend
- `domStorageEnabled = true` — localStorage stores theme and language preferences
- `mediaPlaybackRequiresUserGesture = false` — allows auto-play of Spotify audio previews
- `allowFileAccess = false` — blocks direct file:// access (security)
- `allowContentAccess = true` — allows content:// URIs from the file chooser
- `setSupportMultipleWindows(true)` — enables `window.open()` for OAuth popups

### Custom URI Schemes & Deep Linking

[Deep Links](https://developer.android.com/training/app-links/deep-linking) allow external apps (like the system browser) to navigate into the SpotyVibe app.

**How it works:**
- An `<intent-filter>` in `AndroidManifest.xml` registers the scheme `spotyvibe://callback`.
- When Spotify's OAuth completes, the browser redirects to `spotyvibe://callback?code=...`.
- Android's intent system delivers this URI to `MainActivity`.
- The Kotlin code extracts the auth code and forwards it to Flask.

**Why this is needed:**
- On desktop, Spotify redirects to `http://127.0.0.1:5000/callback` — the browser can reach localhost.
- On Android, the system browser runs in a separate process and cannot reach `127.0.0.1` inside the app. The custom URI scheme bridges this gap.

### Server-Sent Events in WebView

The WebView supports [SSE](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events), which the frontend uses for real-time playlist generation progress. No special Android configuration is needed — the WebView's Chromium engine handles SSE natively via the `fetch()` + `ReadableStream` API.

---


## Gradle Build Configuration

### Plugin Stack

The project uses three Gradle plugins:

| Plugin | ID | Version | Purpose |
|---|---|---|---|
| Android Gradle Plugin | `com.android.application` | 8.2.2 | Compiles Android resources, builds APK |
| Kotlin Android | `org.jetbrains.kotlin.android` | 1.9.22 | Compiles Kotlin source files |
| Chaquopy | `com.chaquo.python` | 15.0.1 | Embeds Python interpreter and pip packages |

Chaquopy requires a dedicated Maven repository: `https://chaquo.com/maven`, configured in the top-level `build.gradle`.

### Android SDK Configuration

| Setting | Value | Why |
|---|---|---|
| `compileSdk` | 34 | Android 14 — latest stable APIs at build time |
| `minSdk` | 26 | Android 8.0 — covers ~95% of active devices; required for WebView features |
| `targetSdk` | 34 | Android 14 — declares compliance with modern security/privacy requirements |

### Chaquopy Python Configuration

```gradle
python {
    version "3.10"
    pip {
        install "flask>=3.0,<4.0"
        install "spotipy>=2.23,<3.0"
        install "python-dotenv>=1.0,<2.0"
        install "markdown>=3.4,<4.0"
    }
}
```

**Key differences from desktop `requirements.txt`:**
- **No `openai` SDK** — replaced by `core/openai_http.py` (direct HTTP via stdlib)
- **No `pytest`, `pytest-playwright`** — testing is desktop-only
- **No `pyinstaller`, `pywebview`, `pillow`** — desktop packaging tools

These pins are intentionally separate from `requirements.txt` to avoid pulling in packages with native Rust extensions that Chaquopy cannot compile.

### NDK Architecture Filters

```gradle
ndk {
    abiFilters "arm64-v8a", "x86_64"
}
```

| ABI | Use Case |
|---|---|
| `arm64-v8a` | Physical Android devices (ARM64 processors) |
| `x86_64` | Android Studio emulators (Intel/AMD host) |

**Note:** Release builds should strip `x86_64` to reduce APK size (~20% savings). It's only needed for emulator testing.

### Dependencies

| Dependency | Version | Purpose |
|---|---|---|
| `androidx.core:core-ktx` | 1.12.0 | Kotlin extensions for Android core APIs |
| `androidx.appcompat:appcompat` | 1.6.1 | Backwards-compatible Activity and Theme support |
| `androidx.webkit:webkit` | 1.10.0 | Modern WebView APIs (file chooser, WebViewClient enhancements) |

### ProGuard

Release builds enable ProGuard (code minification/obfuscation). The rules file preserves Chaquopy bridge classes:

```pro
-keep class com.chaquo.python.** { *; }
```

Without this rule, ProGuard would obfuscate the Python bridge classes, breaking the Kotlin↔Python interface.

---

## Android Manifest & Intents

### Permissions

```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
```

| Permission | Why |
|---|---|
| `INTERNET` | Flask server binding + external API calls (OpenAI, Spotify) |
| `ACCESS_NETWORK_STATE` | Network availability checks (good practice for API calls) |

### Application Configuration

```xml
<application
    android:allowBackup="true"
    android:usesCleartextTraffic="true"
    android:theme="@style/Theme.SpotyVibe">
```

| Attribute | Value | Why |
|---|---|---|
| `allowBackup` | true | Allows Android system backup of app data |
| `usesCleartextTraffic` | true | Permits HTTP (not HTTPS) to localhost — required for Flask on `127.0.0.1` |
| `theme` | Theme.SpotyVibe | Custom dark theme matching the web UI |

**Why `usesCleartextTraffic=true`?** Android 9+ blocks cleartext (HTTP) traffic by default. The Flask server runs on `http://127.0.0.1:5000` (not HTTPS). This flag is safe because the traffic never leaves the device — it's localhost-only.

### Activity Configuration

```xml
<activity
    android:name=".MainActivity"
    android:exported="true"
    android:launchMode="singleTask"
    android:configChanges="orientation|screenSize|keyboardHidden"
    android:windowSoftInputMode="adjustResize">
```

| Attribute | Value | Why |
|---|---|---|
| `exported` | true | Allows external intents (OAuth callbacks from Spotify) |
| `launchMode` | singleTask | Single instance — prevents multiple Activities and Flask servers |
| `configChanges` | orientation, screenSize, keyboardHidden | Activity survives rotation without recreation (preserves WebView state) |
| `windowSoftInputMode` | adjustResize | Resizes WebView when the soft keyboard appears (inputs stay visible) |

**Why `singleTask`?** Without it, each OAuth callback could create a new Activity instance, duplicating the WebView and potentially starting a second Flask server.

### Intent Filters

**1. Launcher (main entry point):**
```xml
<intent-filter>
    <action android:name="android.intent.action.MAIN" />
    <category android:name="android.intent.category.LAUNCHER" />
</intent-filter>
```

**2. OAuth callback (deep link from Spotify):**
```xml
<intent-filter>
    <action android:name="android.intent.action.VIEW" />
    <category android:name="android.intent.category.DEFAULT" />
    <category android:name="android.intent.category.BROWSABLE" />
    <data android:scheme="spotyvibe" android:host="callback" />
</intent-filter>
```

Matches `spotyvibe://callback?code=...&state=...` — triggered when Spotify OAuth redirects back after user grants permission.

---

## Resources & Styling

### Theme Configuration

```xml
<style name="Theme.SpotyVibe" parent="Theme.AppCompat.NoActionBar">
    <item name="android:statusBarColor">#050608</item>
    <item name="android:navigationBarColor">#050608</item>
    <item name="android:windowBackground">#050608</item>
</style>
```

- **Parent:** `Theme.AppCompat.NoActionBar` — no traditional action bar (the UI is entirely in the WebView)
- **Color `#050608`:** Near-black, matching the web app's `--bg-main` CSS variable
- Applied to status bar, navigation bar, and window background for a seamless dark appearance during splash and loading

### Layout — Three-Layer View Stack

The layout (`activity_main.xml`) uses a `FrameLayout` with three overlapping views, toggled by visibility:

```
┌─────────────────────────────────┐
│  FrameLayout (background #050608)│
│                                  │
│  ┌────────────────────────────┐  │
│  │ 1. splashView (VISIBLE)   │  │  ← Shown while Flask starts
│  │    "SpotyVibe" title       │  │     Spotify green (#1ed760)
│  │    "Starting server…"      │  │     ProgressBar spinner
│  │    ProgressBar             │  │
│  └────────────────────────────┘  │
│                                  │
│  ┌────────────────────────────┐  │
│  │ 2. errorView (GONE)       │  │  ← Shown if Flask fails (30s timeout)
│  │    ⚠️ icon + error text    │  │     "Retry" button
│  └────────────────────────────┘  │
│                                  │
│  ┌────────────────────────────┐  │
│  │ 3. WebView (GONE)         │  │  ← Shown when Flask is ready
│  │    Flask content           │  │     Full screen
│  └────────────────────────────┘  │
└─────────────────────────────────┘
```

**State transitions:**
1. **App start:** splashView visible, others gone → Flask polling begins
2. **Flask ready:** splashView gone, WebView visible → loads Flask URL
3. **Flask timeout:** splashView gone, errorView visible → retry button available

---

## Kotlin Implementation — MainActivity

`MainActivity.kt` is the single Activity — it manages the entire Android layer.

### Flask Server Lifecycle

#### Starting the Server

```kotlin
companion object {
    private const val FLASK_URL = "http://127.0.0.1:5000"
    private const val MAX_RETRIES = 60
    private const val RETRY_DELAY_MS = 500L
    @Volatile private var flaskStarted = false
}
```

`startFlaskServer()` flow:

1. **Initialize Python** via Chaquopy (`Python.start(AndroidPlatform(this))`)
2. **Check `flaskStarted` flag** — if `true` (process survived Activity recreation), skip startup and show WebView immediately
3. **Set `flaskStarted = true`** to guard against re-entry
4. **Spawn Flask daemon thread:**
   ```kotlin
   flaskThread = Thread({
       py.getModule("spotyvibe_bootstrap").callAttr("start", filesDir.absolutePath)
   }, "flask-server").apply {
       isDaemon = true
       start()
   }
   ```
5. **Spawn waiter thread** that polls Flask health

**Why `@Volatile`?** The `flaskStarted` flag is read/written from multiple threads (UI thread, waiter thread). `@Volatile` ensures visibility across threads without a full lock.

**Why daemon thread?** A daemon thread is killed when the JVM exits (Activity destroyed). This prevents orphan Flask processes.

#### Waiting for Flask

```kotlin
fun waitForFlask(): Boolean {
    for (i in 1..MAX_RETRIES) {           // 60 attempts
        try {
            val conn = URL(FLASK_URL).openConnection() as HttpURLConnection
            conn.connectTimeout = 400
            conn.readTimeout = 400
            conn.requestMethod = "GET"
            val code = conn.responseCode
            conn.disconnect()
            if (code == 200) return true
        } catch (_: Exception) { }
        Thread.sleep(RETRY_DELAY_MS)        // 500ms between attempts
    }
    return false                            // Timeout after 30 seconds
}
```

**Strategy:** HTTP GET to `http://127.0.0.1:5000/` every 500ms. If Flask returns 200 → server is ready. After 60 retries (30 seconds) → show error view with retry button.

**Why polling (not callbacks)?** Chaquopy's Python runs in a separate thread with no callback mechanism to Kotlin. Polling is the simplest reliable approach.

#### Error Recovery

If Flask fails to start within 30 seconds, the error view shows a "Retry" button:

```kotlin
fun retryFlaskServer() {
    flaskStarted = false   // Reset guard
    // Show splash, hide error, restart Flask
    startFlaskServer()
}
```

### WebView Configuration & Security

```kotlin
webView.settings.apply {
    javaScriptEnabled = true
    domStorageEnabled = true
    mediaPlaybackRequiresUserGesture = false
    allowFileAccess = false
    allowContentAccess = true
    javaScriptCanOpenWindowsAutomatically = true
    setSupportMultipleWindows(true)
}
```

| Setting | Value | Why |
|---|---|---|
| `javaScriptEnabled` | true | The SPA frontend requires JavaScript |
| `domStorageEnabled` | true | localStorage stores theme, language, session state |
| `mediaPlaybackRequiresUserGesture` | false | Auto-play Spotify audio previews without user tap |
| `allowFileAccess` | false | **Security:** blocks direct `file://` protocol access from JavaScript |
| `allowContentAccess` | true | Allows `content://` URIs — needed for file chooser results |
| `javaScriptCanOpenWindowsAutomatically` | true | Enables `window.open()` for OAuth popups |
| `setSupportMultipleWindows` | true | Creates popup WebViews for the OAuth flow |

### WebViewClient — URL Routing

The `WebViewClient` controls which URLs load in the WebView vs the system browser:

```kotlin
override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
    val url = request.url.toString()

    if (url.startsWith(FLASK_URL)) {
        // Detect onboarding completion (navigating from /onboarding to /)
        val fromOnboarding = view.url?.contains("/onboarding") == true
        val toMain = !url.contains("/onboarding")
        if (fromOnboarding && toMain) {
            getSharedPreferences("spotyvibe", Context.MODE_PRIVATE)
                .edit().putBoolean("onboardingCompleted", true).apply()
        }
        return false  // Load in WebView
    }

    // External URLs → system browser
    startActivity(Intent(Intent.ACTION_VIEW, request.url))
    return true
}
```

**Rules:**
- `http://127.0.0.1:5000/*` → load inside WebView (return `false`)
- Everything else (Spotify URLs, external links) → open in system browser (return `true`)
- **Onboarding detection:** When navigating from `/onboarding` to `/`, set `onboardingCompleted = true` in SharedPreferences

### WebChromeClient — File Chooser & Popups

#### File Chooser (Profile Import)

When the user taps a file input in the web UI, Android's file picker opens:

```kotlin
override fun onShowFileChooser(
    webView: WebView?,
    filePathCallback: ValueCallback<Array<Uri>>?,
    fileChooserParams: WebChromeClient.FileChooserParams?
): Boolean {
    fileChooserCallback?.onReceiveValue(null)  // Cancel any pending
    fileChooserCallback = filePathCallback

    val intent = Intent(Intent.ACTION_GET_CONTENT).apply {
        addCategory(Intent.CATEGORY_OPENABLE)
        type = "*/*"
        putExtra(Intent.EXTRA_MIME_TYPES, arrayOf(
            "application/json", "text/json", "text/plain"
        ))
    }

    fileChooserLauncher.launch(Intent.createChooser(intent, "Select profile JSON"))
    return true
}
```

**Flow:**
1. JavaScript `<input type="file">` triggers Android's `onShowFileChooser()`
2. Launch Storage Access Framework file picker (filters to JSON/text MIME types)
3. User selects file → callback returns URI array to JavaScript
4. JavaScript reads the file and POSTs to `/api/profile/import`

Uses `registerForActivityResult(ActivityResultContracts.StartActivityForResult())` — the modern Activity Result API (not the deprecated `onActivityResult`).

#### Console Message Forwarding

```kotlin
override fun onConsoleMessage(msg: ConsoleMessage?): Boolean {
    msg?.let { Log.d(TAG, "JS [${it.sourceId()}:${it.lineNumber()}] ${it.message()}") }
    return true
}
```

Forwards JavaScript `console.log()` to Android Logcat with source file and line number. Essential for debugging the web frontend on Android.

#### window.open() Popup Handling (OAuth)

```kotlin
override fun onCreateWindow(view: WebView?, isDialog: Boolean,
    isUserGesture: Boolean, resultMsg: Message?): Boolean {

    val popupWebView = WebView(this@MainActivity).apply {
        webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView,
                request: WebResourceRequest): Boolean {
                val url = request.url.toString()
                if (url.startsWith(FLASK_URL)) {
                    webView.loadUrl(url)       // Callback → main WebView
                } else {
                    startActivity(Intent(Intent.ACTION_VIEW, request.url))
                }
                view.destroy()                 // Clean up popup immediately
                return true
            }
        }
    }

    val transport = resultMsg?.obj as? WebView.WebViewTransport ?: return false
    transport.webView = popupWebView
    resultMsg.sendToTarget()
    return true
}
```

**Purpose:** Handle the Spotify OAuth popup flow without a persistent popup WebView.

**Flow:**
1. Frontend calls `window.open(spotifyAuthUrl)` for OAuth
2. Android creates a temporary popup WebView
3. The popup intercepts the first navigation:
   - If localhost (callback) → load in main WebView
   - If external (Spotify login page) → open in system browser
4. Popup is destroyed immediately to free memory

**Why not just `startActivity`?** The `window.open()` call expects a WebView transport reply. Without handling `onCreateWindow`, the popup silently fails and OAuth never starts.

### Download Management & Security

```kotlin
webView.setDownloadListener { url, userAgent, contentDisposition, mimeType, _ ->
    val uri = Uri.parse(url)
    val isTrustedExport = (
        uri.scheme == "http" &&
        uri.host == "127.0.0.1" &&
        uri.port == 5000 &&
        uri.path == "/api/profile/export"
    )

    if (!isTrustedExport) {
        Log.w(TAG, "Blocked download from untrusted URL: $url")
        return@setDownloadListener
    }

    val request = DownloadManager.Request(uri).apply {
        setMimeType(mimeType)
        addRequestHeader("User-Agent", userAgent)
        setDescription("SpotyVibe profile export")
        setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
        setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, filename)
    }
    (getSystemService(DOWNLOAD_SERVICE) as DownloadManager).enqueue(request)
}
```

**Security:** **Whitelist-only downloads.** Only `http://127.0.0.1:5000/api/profile/export` is permitted. All other download URLs are blocked and logged as warnings. This prevents the WebView from downloading arbitrary files.

The file is saved to the device's Downloads folder via `DownloadManager`, which shows a system notification on completion.

### OAuth Deep-Link Handling

```kotlin
private fun handleOAuthIntent(intent: Intent?) {
    intent?.data?.let { uri ->
        if (uri.scheme == "spotyvibe" && uri.host == "callback") {
            val code = uri.getQueryParameter("code")
            if (code != null) {
                val flaskCallback = Uri.Builder()
                    .scheme("http").authority("127.0.0.1:5000")
                    .path("/callback")
                    .appendQueryParameter("code", code)
                    .apply {
                        uri.getQueryParameter("state")?.let {
                            appendQueryParameter("state", it)
                        }
                    }
                    .build().toString()
                webView.loadUrl(flaskCallback)
            } else {
                val error = uri.getQueryParameter("error") ?: "unknown_error"
                val flaskError = Uri.Builder()
                    .scheme("http").authority("127.0.0.1:5000")
                    .path("/callback")
                    .appendQueryParameter("error", error)
                    .build().toString()
                webView.loadUrl(flaskError)
            }
        }
    }
}
```

**Flow:**
1. Spotify redirects to `spotyvibe://callback?code=AUTH_CODE&state=STATE`
2. Android matches the intent filter → delivers to MainActivity
3. `handleOAuthIntent()` extracts `code` (or `error`) query parameters
4. Rebuilds as `http://127.0.0.1:5000/callback?code=...&state=...` using `Uri.Builder` (safe encoding)
5. Loads the URL in the WebView → Flask processes the OAuth callback

**Called from both:**
- `onCreate()` — cold start (process was killed, Activity recreated)
- `onNewIntent()` — warm resume (Activity already running)

### Profile Import via Share Intent

```kotlin
private fun handleShareIntent(intent: Intent?) {
    if (intent?.action != Intent.ACTION_SEND) return
    val uri = intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM) ?: return
    val mime = intent.type ?: ""
    if (!mime.contains("json") && !mime.contains("text") && !mime.contains("octet")) return

    Thread({
        val bytes = contentResolver.openInputStream(uri)?.readBytes() ?: return@Thread
        val json = String(bytes, Charsets.UTF_8)

        val conn = URL("$FLASK_URL/api/profile/import").openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        conn.doOutput = true
        conn.setRequestProperty("Content-Type", "application/json")
        conn.outputStream.write("""{"profile":$json}""".toByteArray(Charsets.UTF_8))
        val code = conn.responseCode
        conn.disconnect()

        runOnUiThread {
            Toast.makeText(this, if (code == 200) "Profile imported successfully"
                else "Profile import failed (HTTP $code)", Toast.LENGTH_LONG).show()
        }
    }, "share-import").apply { isDaemon = true; start() }
}
```

**Flow:**
1. User shares a JSON file from another app (Files, Google Drive, etc.) → Android routes `ACTION_SEND` to SpotyVibe
2. MIME type validated (must contain `json`, `text`, or `octet`)
3. File content read via `contentResolver` (Storage Access Framework-compatible)
4. Posted to `/api/profile/import` — same endpoint as manual import
5. Toast notification shows success/failure

**Why Content URIs?** Android's scoped storage (Android 10+) doesn't allow direct file path access. Content URIs via `ContentResolver` work with any file provider (Google Drive, Files app, email attachments, etc.).

**Why daemon thread?** File I/O and HTTP POST are blocking operations. Running on the UI thread would cause an ANR (Application Not Responding) error.

### Back Press Handling

```kotlin
private fun registerBackPress() {
    onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
        override fun handleOnBackPressed() {
            if (webView.canGoBack()) {
                webView.goBack()            // Navigate back in WebView history
            } else {
                isEnabled = false
                onBackPressedDispatcher.onBackPressed()  // Exit activity
            }
        }
    })
}
```

- **Back button with WebView history:** Go back in the WebView (like a browser)
- **At the start of history:** Exit the activity

Uses the modern `OnBackPressedDispatcher` API (not the deprecated `onBackPressed()` override).

### Activity Lifecycle

```kotlin
override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    setContentView(R.layout.activity_main)
    // 1. Find views (splash, WebView, error)
    // 2. Wire retry button
    // 3. Configure WebView security
    // 4. Register back-press handler
    // 5. Start Flask server (async)
    // 6. Handle OAuth intent (if cold start via deep link)
    // 7. Handle share intent (if cold start via file share)
}

override fun onNewIntent(intent: Intent?) {
    super.onNewIntent(intent)
    handleOAuthIntent(intent)     // Warm resume from OAuth
    handleShareIntent(intent)     // Warm resume from file share
}

override fun onDestroy() {
    flaskThread?.interrupt()      // Stop Flask
    flaskThread = null
    webView.destroy()             // Release WebView resources
    super.onDestroy()
}
```

**Key lifecycle decisions:**
- **No `onPause`/`onResume` WebView management** — The WebView keeps running when the app is backgrounded. This is intentional: Flask stays alive and SSE connections remain open.
- **`configChanges` in manifest** prevents Activity recreation on rotation — preserves WebView state and Flask connection.
- **Daemon thread for Flask** — killed automatically when the process exits.

---

## Python Bootstrapping

### Entry Point: `spotyvibe_bootstrap.py`

```python
import os, sys

def start():
    os.environ.setdefault("SPOTYVIBE_FILES_DIR",
                          os.path.dirname(os.path.abspath(__file__)))
    from app import app
    app.run(host="127.0.0.1", port=5000,
            debug=False, use_reloader=False, threaded=True)

if __name__ == "__main__":
    start()
```

**Why these flags?**

| Flag | Value | Reason |
|------|-------|--------|
| `debug` | `False` | Debug mode enables the interactive debugger, useless on Android |
| `use_reloader` | `False` | The reloader spawns a child process — Chaquopy doesn't support `multiprocessing` properly |
| `threaded` | `True` | SSE requires concurrent request handling (one connection per client) |

### Android Detection: `config.py`

```python
IS_ANDROID = hasattr(sys, "getandroidapilevel")
```

This stdlib attribute is set by Chaquopy's Python interpreter. Used to branch platform-specific paths:

```python
def _get_app_dir():
    if IS_ANDROID:
        base = os.environ.get("SPOTYVIBE_FILES_DIR", ".")
    elif IS_WINDOWS_EXE:
        base = os.path.join(os.environ.get("LOCALAPPDATA", "."), "spotyvibe")
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(base, exist_ok=True)
    return base
```

### Storage Paths on Android

| Item | Desktop Path | Android Path |
|------|-------------|--------------|
| Credentials | `%LOCALAPPDATA%\spotyvibe\.credentials` | `/data/data/com.spotyvibe.app/files/.credentials` |
| Spotify cache | `%LOCALAPPDATA%\spotyvibe\.spotify-cache` | `/data/data/com.spotyvibe.app/files/.spotify-cache` |
| Music profile | `%LOCALAPPDATA%\spotyvibe\personalized_music_profile.json` | `/data/data/com.spotyvibe.app/files/personalized_music_profile.json` |
| Settings | `%LOCALAPPDATA%\spotyvibe\settings.conf` | `/data/data/com.spotyvibe.app/files/settings.conf` |
| Song list | `%LOCALAPPDATA%\spotyvibe\song_list.json` | `/data/data/com.spotyvibe.app/files/song_list.json` |

All paths are inside Android's **internal storage** (`Context.getFilesDir()`), which is:
- **Sandboxed** — other apps cannot access them
- **Backed up** by Android Auto Backup (if enabled)
- **Deleted** when the app is uninstalled

### Features Disabled on Android

```python
# config.py
if IS_ANDROID:
    OPEN_BROWSER_ON_START = False      # WebView IS the browser
    DESKTOP_LAUNCH_FEATURES = False    # No system tray, no window management
```

The desktop launcher (`desktop_launcher.py`) is skipped entirely — Android's Activity *is* the launcher.

---

## Android Onboarding Flow

SpotyVibe has a first-run onboarding screen (credentials setup + Spotify connection). On Android, it uses a **dual-persisted** onboarding state:

### Dual Persistence

| Store | Location | Purpose |
|-------|----------|---------|
| `SharedPreferences` | `onboarding_prefs.xml` (Android internal) | Kotlin-side flag — survives Activity restart |
| `settings.conf` | Python internal storage | Flask-side flag — authoritative after first run |

```kotlin
// Check both stores
val androidDone = prefs.getBoolean("onboarding_done", false)
// Flask returns {"onboarding_completed": true/false} from settings.conf
val flaskDone = checkFlaskOnboarding()
val showOnboarding = !androidDone && !flaskDone
```

**Why two stores?** The Kotlin layer decides which URL to load *before* Flask is fully ready. `SharedPreferences` is instantaneous; polling Flask would require the server to be running. But the authoritative state is in `settings.conf` because Flask manages the onboarding flow (saving credentials, completing Spotify OAuth).

After onboarding completes:
1. Flask sets `onboarding_completed = true` in `settings.conf`
2. JavaScript calls `Android.onboardingDone()` (WebView JavaScript interface)
3. Kotlin sets `SharedPreferences("onboarding_done", true)`
4. Both stores are now in sync

---

## OAuth Flow on Android

The Spotify OAuth flow is significantly different on Android because the WebView cannot handle redirects to external identity providers securely.

### 12-Step Flow

```
User taps "Connect Spotify"
    ↓
[1] JavaScript calls /api/spotify/login
    ↓
[2] Flask generates Spotify auth URL (accounts.spotify.com)
    ↓
[3] Flask returns {"auth_url": "https://accounts.spotify.com/authorize?...redirect_uri=spotyvibe://callback..."}
    ↓
[4] JavaScript calls Android.openExternal(auth_url)
    ↓
[5] Kotlin opens system browser: Intent(ACTION_VIEW, Uri.parse(auth_url))
    ↓
[6] User logs in to Spotify in Chrome/Firefox (system browser)
    ↓
[7] Spotify redirects to spotyvibe://callback?code=AUTH_CODE&state=STATE
    ↓
[8] Android matches intent filter → delivers to MainActivity
    ↓
[9] handleOAuthIntent() rebuilds as http://127.0.0.1:5000/callback?code=...
    ↓
[10] WebView loads the Flask callback URL
    ↓
[11] Flask exchanges code for access/refresh tokens via Spotify API
    ↓
[12] Flask redirects to main page → user is connected
```

### Desktop vs Android Comparison

| Aspect | Desktop | Android |
|--------|---------|---------|
| Browser | System default | System browser (Chrome, Firefox) |
| Redirect URI | `http://127.0.0.1:5000/callback` | `spotyvibe://callback` |
| OAuth return | Redirect back to localhost | Deep link to Activity |
| Cookie isolation | Same browser | WebView ↔ Browser are isolated |
| Token storage | `.spotify-cache` in `%LOCALAPPDATA%` | `.spotify-cache` in internal storage |

**Critical implication:** The WebView and system browser do **not** share cookies or sessions. The OAuth flow *must* go through the system browser because Spotify may require an existing session or CAPTCHA that the WebView sandbox cannot handle.

---

## Chaquopy Constraints & Dependency Strategy

### The Rust Extension Problem

Modern Python packages increasingly use Rust extensions via `maturin` or `setuptools-rust`:

```
openai → pydantic v2 → pydantic-core (Rust)
openai → jiter (Rust)
```

Chaquopy compiles native extensions for Android ABIs (arm64-v8a, x86_64) using its own cross-compilation toolchain. **Rust-based extensions are not supported** because:
1. Chaquopy's toolchain targets C/C++ only
2. Rust cross-compilation requires `cargo` + Android NDK target setup
3. `pydantic-core` and `jiter` have no pre-built Android wheels

### The Solution: `core/openai_http.py`

Instead of depending on the `openai` SDK, SpotyVibe uses a direct HTTP client built with Python's stdlib:

```python
import json
import urllib.request

def chat_completion(messages, model="gpt-4o-mini", ...):
    body = json.dumps({"model": model, "messages": messages, ...}).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())
```

**Zero native dependencies.** Works identically on desktop, Android, and PyInstaller builds.

### Pip Pins Comparison

| Package | `requirements.txt` (Desktop) | `build.gradle` (Android) | Notes |
|---------|------------------------------|--------------------------|-------|
| `flask` | `>=3.0` | `version = "3.1.1"` | Exact pin for reproducibility |
| `spotipy` | `>=2.23` | `version = "2.25.1"` | Exact pin |
| `python-dotenv` | `>=1.0` | `version = "1.1.0"` | Exact pin |
| `markdown` | `>=3.5` | `version = "3.8"` | For help page rendering |
| `openai` | **Not installed** | **Not installed** | Replaced by `core/openai_http.py` |

**Why exact pins on Android?** Chaquopy downloads pre-built wheels from its own repository. Version ranges could pull incompatible versions. Desktop uses ranges for flexibility since pip resolves natively.

---

## Build Script & APK Packaging

### `build-tools/build_apk.sh`

```bash
#!/bin/bash
BUILD_TYPE="${1:-debug}"  # debug or release

# Phase 1: Clean
rm -rf android/app/src/main/python/
mkdir -p android/app/src/main/python/

# Phase 2: Copy Python sources
cp app.py config.py version.py spotyvibe_bootstrap.py \
   android/app/src/main/python/
cp -r core/ prompts/ data/ frontend/ documentation/ \
   android/app/src/main/python/

# Phase 3: Assemble
cd android/
./gradlew assemble${BUILD_TYPE^}
```

**Phase 1 — Clean:** Ensures no stale Python files remain from previous builds.

**Phase 2 — Copy:** Flattens the project structure into the Chaquopy source directory. The Python code that runs on Android is an exact copy of the desktop code — same `app.py`, same `core/`, same `frontend/templates/` and `frontend/static/`.

**Phase 3 — Assemble:** Gradle triggers Chaquopy, which:
1. Creates a Python virtual environment for the target ABIs
2. Installs pip packages from `build.gradle` pins
3. Compiles `.py` files to `.pyc` bytecode
4. Packages everything into the APK's `assets/` directory
5. Bundles the Chaquopy Python interpreter (libpython3.10.so) for each ABI

### Output

| Build Type | APK Location | Size |
|-----------|-------------|------|
| Debug | `android/app/build/outputs/apk/debug/app-debug.apk` | ~45 MB |
| Release | `android/app/build/outputs/apk/release/app-release.apk` | ~30 MB (with ProGuard) |

The size difference comes from ProGuard shrinking Kotlin code and the debug APK including debug symbols.

---

## Security Architecture

### Network Security

| Control | Implementation |
|---------|----------------|
| Localhost only | Flask binds to `127.0.0.1` (not `0.0.0.0`) |
| No cleartext | `android:usesCleartextTraffic="true"` applies only to localhost |
| HTTPS external | All Spotify/OpenAI calls use HTTPS |

### WebView Security

| Control | Implementation |
|---------|----------------|
| No file access | `allowFileAccess = false` |
| No content access | `allowContentAccess = false` |
| Localhost navigation only | `shouldOverrideUrlLoading` blocks non-localhost URLs |
| External URLs | Opened in system browser via `Intent(ACTION_VIEW)` |
| JavaScript | Enabled (required for the SPA) |

### Intent Security

| Control | Implementation |
|---------|----------------|
| URI scheme | `spotyvibe://` — unique to this app |
| Share MIME filter | Only `application/json`, `text/*`, `application/octet-stream` |
| Import validation | Server-side size limit and JSON schema validation |

### Credential Storage

| Control | Implementation |
|---------|----------------|
| Location | Android internal storage (sandboxed, not on SD card) |
| Format | INI file (`.credentials`) via Python `configparser` |
| Access | Only this app's process can read/write |
| Encryption | Relies on Android's disk encryption (FBE or FDE) |

---

## General Use Cases for This Architecture

The Chaquopy + WebView + localhost Flask pattern is suitable for:

1. **Porting existing Flask/Django apps to mobile** — Minimal code changes; the web frontend works as-is in a WebView.

2. **AI-powered apps needing a Python backend** — Python's ML/NLP ecosystem (transformers, langchain, etc.) runs natively via Chaquopy.

3. **Rapid prototyping** — Develop and debug the web app on desktop, then wrap it in an APK with minimal Android-specific code.

4. **Apps with complex server logic** — OAuth flows, API orchestration, data processing — all handled by Python on-device instead of a remote server.

5. **Privacy-sensitive apps** — All processing happens locally. No data leaves the device except explicit API calls (Spotify, OpenAI).

---

## Potential Pitfalls

| Pitfall | Description | Mitigation |
|---------|-------------|------------|
| **APK size** | Chaquopy bundles a full Python interpreter + pip packages (~30-45 MB) | Strip unused ABIs for release (arm64-v8a only) |
| **Cold start time** | Python interpreter initialization adds 2-4 seconds | Splash screen with polling; pre-extract on first install |
| **Background killing** | Android may kill the process when backgrounded | Flask is stateless (file-backed); reconnect on resume |
| **Rust extensions** | Packages depending on Rust (pydantic v2, jiter, tiktoken) won't compile | Use stdlib alternatives or pure-Python packages |
| **localStorage** | WebView localStorage may be cleared on app update | Use Flask-backed storage for persistent data |
| **Onboarding sync** | Kotlin SharedPreferences and Python settings.conf can drift | Check both stores; Flask is authoritative |
| **getParcelableExtra** | Deprecated in API 33+ (use type-safe alternative) | Currently using compat version; works but shows lint warning |
| **Reloader** | Flask reloader uses `multiprocessing` — not supported by Chaquopy | Always set `use_reloader=False` |
| **Thread safety** | Flask development server is not production-grade | `threaded=True` is sufficient for single-user localhost; no concurrent users |

---

## Documentation & Learning Resources

### Android & WebView

- [Chaquopy Documentation](https://chaquo.com/chaquopy/doc/current/) — Python on Android via Gradle
- [Android WebView Guide](https://developer.android.com/develop/ui/views/layout/webapps/webview) — Official WebView configuration
- [WebViewClient Reference](https://developer.android.com/reference/android/webkit/WebViewClient) — URL interception and page lifecycle
- [WebChromeClient Reference](https://developer.android.com/reference/android/webkit/WebChromeClient) — File chooser, popups, console
- [Android Deep Links](https://developer.android.com/training/app-links/deep-linking) — Custom URI scheme handling
- [Android Intent Filters](https://developer.android.com/guide/components/intents-filters) — Intent matching and routing
- [OnBackPressedDispatcher](https://developer.android.com/guide/navigation/custom-back/predictive-back-gesture) — Modern back navigation
- [Android Storage](https://developer.android.com/training/data-storage) — Internal vs external storage, scoped storage

### Backend & API

- [Flask Documentation](https://flask.palletsprojects.com/) — Web framework
- [Spotify Web API Reference](https://developer.spotify.com/documentation/web-api) — All endpoints
- [Spotipy Documentation](https://spotipy.readthedocs.io/) — Python Spotify client
- [OpenAI API Reference](https://platform.openai.com/docs/api-reference) — Chat completions
- [Python `urllib.request`](https://docs.python.org/3/library/urllib.request.html) — HTTP client used by `openai_http.py`
