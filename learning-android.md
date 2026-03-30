# Learning Android Development: Embedded Python & WebView Architecture

This document serves as a comprehensive guide to understanding the architecture used to package the SpotyVibe Flask application into a native Android APK. It explains the core technologies, their roles, general use cases, and provides useful documentation links.

## 1. Architectural Overview

The SpotyVibe Android app uses a **hybrid local-server architecture**. Instead of rewriting the existing Python backend (Flask) into Kotlin or Java, or hosting it on a cloud server, the entire Python runtime is embedded inside the Android app. 

1. **Native Shell (Kotlin):** A minimal Android app that boots up and manages the lifecycle, handles an onboarding flow on first launch, processes share intents for profile import, and enforces download restrictions for security.
2. **Local Backend (Chaquopy + Python):** The app spins up a background thread that runs the Flask server locally on `127.0.0.1:5000`.
3. **Frontend (WebView):** The main UI is an Android `WebView` that navigates to the local Flask server, rendering the existing HTML/CSS/JS exactly as a desktop browser would.

The Android build is intentionally pinned for reproducibility: Android Gradle Plugin 8.2.2, Kotlin 1.9.22, Chaquopy 15.0.1, compile/target SDK 34, min SDK 26, Java 17, and Python 3.10.

---

## 2. Key Technologies

### 2.1 Chaquopy (Embedded Python)
[Chaquopy](https://chaquo.com/chaquopy/) is a Gradle plugin that seamlessly embeds CPython into an Android app.
- **How it works:** It bundles the Python interpreter and specifies pinned pip dependencies in `android/app/build.gradle`. At runtime, the Kotlin/Java code can start the interpreter and execute Python scripts.
- **Why it was used:** It allowed the SpotyVibe backend (which relies heavily on Python packages like `openai`, `spotipy`, and `flask`) to run unmodified directly on the user's phone, avoiding cloud hosting costs and keeping API keys secure on the device.

### 2.2 Android WebView
[Android WebView](https://developer.android.com/develop/ui/views/layout/webapps/webview) is a system component for the Android OS that allows Android apps to display web content.
- **How it works:** It acts as an embedded minimal Chrome browser. In this architecture, it interacts with the locally hosted Flask app via `127.0.0.1`.
- **Configuration:** Features like JavaScript, DOM storage (localStorage), and custom URL interceptors (`WebViewClient`) must be explicitly enabled and configured via Kotlin.
- **localStorage persistence:** The WebView's localStorage stores UI preferences (theme, language). This works because `domStorageEnabled = true` is set in the WebView configuration.

### 2.3 Custom URI Schemes & Deep Linking
[Deep Links](https://developer.android.com/training/app-links/deep-linking) allow users to navigate directly into specific parts of an Android app using URLs.
- **How it works:** By defining an `<intent-filter>` in the `AndroidManifest.xml` (e.g., `spotyvibe://callback`), the Android OS knows to wake up the app when the system browser redirects to that URL.
- **Use case here:** Spotify's OAuth 2.0 flow requires the user to log in via the system browser (Chrome). Once authenticated, Spotify redirects to `spotyvibe://callback`. The native app intercepts this Intent via `onNewIntent()` and forwards the auth token back to the local Flask server.

### 2.4 Server-Sent Events (SSE)
[Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events) are used to stream real-time updates from a server to a client over a single HTTP connection. 
- **Use case here:** Used during the AI playlist generation to feed real-time generation progress to the UI without relying on WebSockets.

---

## 3. General Use Cases for this Architecture

Choosing an Embedded Python + WebView architecture instead of Native UI (Jetpack Compose/XML) or Cross-Platform frameworks (Flutter/React Native) makes sense for specific scenarios:

1. **Heavy Python Ecosystem Reliance:** Apps that rely heavily on data science, AI/ML, or specific Python-only libraries (e.g., Pandas, OpenCV, specific AI wrappers) can run locally without needing a cloud backend.
2. **Privacy & Offline First:** Because the backend is on the phone, sensitive data (like API keys, personal profiles) never leaves the device. (Note: SpotyVibe still needs the internet for external API calls, but the data storage is strictly local).
3. **Rapid Porting of Web Apps to Mobile:** Developers can convert a Flask, Django, or FastAPI application into a native mobile app quickly with near-zero changes to the business logic or frontend code.
4. **Bypassing Cloud/Server Costs:** Distributing the compute load to the client’s device instead of paying for PaaS (Platform as a Service) hosting for hundreds of users.

---

## 4. Documentation & Learning Resources

* **Chaquopy Official Documentation:** [https://chaquo.com/chaquopy/doc/current/](https://chaquo.com/chaquopy/doc/current/)
* **Android Web Apps (WebView) Guide:** [https://developer.android.com/develop/ui/views/layout/webapps/webview](https://developer.android.com/develop/ui/views/layout/webapps/webview)
* **Android Intents and Intent Filters (Deep Links):** [https://developer.android.com/guide/components/intents-filters](https://developer.android.com/guide/components/intents-filters)
* **Handling App Links and Deep Links:** [https://developer.android.com/training/app-links](https://developer.android.com/training/app-links)
* **Flask Official Documentation:** [https://flask.palletsprojects.com/](https://flask.palletsprojects.com/)
* **MDN Web Docs - Server-Sent Events:** [https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)

---

## 5. Android Onboarding Flow

The Android app includes a multi-page swipeable onboarding for first-time users:

**How it works:**
- `MainActivity.kt` loads `/onboarding` on app start.
- The backend checks the `ONBOARDING_COMPLETED` flag in config — if already done, the frontend redirects to `/`.
- `templates/onboarding.html` implements a 3-page swipeable flow:
  - **Page 1 (Intro):** App logo, name, feature highlights.
  - **Page 2 (Credentials):** OpenAI API key, Spotify Client ID/Secret inputs with inline validation.
  - **Page 3 (Spotify + Import):** Connect Spotify button + Import preference profile button.
- Navigation uses CSS scroll-snap for horizontal swiping with touch event handlers (50px threshold).
- Buttons: Skip (all pages), Next (pages 1-2), Close (page 3).
- Completion: `POST /api/onboarding/complete` persists the flag, then redirects to `/`.

**Key decisions:**
- Onboarding is HTML/JS in the WebView, not native Kotlin — reuses existing Flask templates and endpoints.
- State is persisted server-side via config (not just localStorage) — survives app data clear.
- Spotify auth during onboarding uses the same deep-link OAuth flow (`spotyvibe://callback`).

---

## 6. Share Intent & File Import

The Android app can receive shared files (JSON profiles) from other apps:

**How it works:**
- `MainActivity.kt` → `handleShareIntent()`:
  1. Extracts `Uri` from `Intent.EXTRA_STREAM`.
  2. Reads file content via `contentResolver.openInputStream()`.
  3. Validates MIME type contains "json", "text", or "octet".
  4. Posts JSON content to `/api/profile/import` endpoint.
  5. Shows Toast notification for success/failure.
- Called from both `onCreate()` (cold start) and `onNewIntent()` (warm resume).

**Key decisions:**
- Uses Content URIs (SAF-compatible) rather than file paths — works with any file provider.
- Import goes through the same validation pipeline as manual import (schema validation, sanitization).

---

## 7. WebView Download Restriction

Downloads from the WebView are restricted to trusted localhost endpoints:

- `setDownloadListener()` in `MainActivity.kt` checks the download URL.
- Only allows URLs starting with `http://127.0.0.1:5000/api/profile/export`.
- All other download URLs are blocked with logging.
- Uses Android `DownloadManager` to save allowed files to the device's Downloads folder.

This prevents the WebView from downloading arbitrary files — only the profile export endpoint is a legitimate download source.

---

## 8. Potential Pitfalls to Watch Out For

If you plan to use this architecture in the future, be aware of:
* **APK Size:** Bundling a CPython runtime usually adds 20-40 MB to the final APK size.
* **Cold Start Time:** Booting a Python runtime inside Android takes a few seconds (2-5s typically). A native splash screen is highly recommended.
* **Lifecycle Management:** Mobile OSs aggressively kill background apps. If the user minimizes the app to check messages, the Android system might kill the Flask background thread unless managed properly.
* **C-Extensions in Python:** While pure Python packages work perfectly out of the box, Python packages that use C/C++ extensions must be pre-compiled for ARM processors. Chaquopy handles many of these, but niche libraries might fail.
* **Deprecated API warnings:** `getParcelableExtra()` without a class parameter is deprecated in API 33+. Use `getParcelableExtra(name, T::class.java)` for forward compatibility.
* **Onboarding state sync:** If the user clears app data, `ONBOARDING_COMPLETED` is reset and onboarding shows again. This is by design — credentials are also cleared, so re-onboarding is appropriate.