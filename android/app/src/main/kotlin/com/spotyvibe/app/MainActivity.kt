package com.spotyvibe.app

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.util.Log
import android.view.View
import android.webkit.ConsoleMessage
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.net.HttpURLConnection
import java.net.URL

class MainActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "SpotyVibe"
        private const val FLASK_URL = "http://127.0.0.1:5000"
        private const val MAX_RETRIES = 60          // up to 30 seconds
        private const val RETRY_DELAY_MS = 500L
        @Volatile private var flaskStarted = false  // survives Activity re-creation
    }

    private lateinit var webView: WebView
    private lateinit var splashView: View
    private var flaskThread: Thread? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        splashView = findViewById(R.id.splashView)
        webView = findViewById(R.id.webView)

        configureWebView()
        registerBackPress()
        startFlaskServer()

        // Handle spotyvibe://callback intent on cold start.
        // If Android killed the process while the user was in Chrome doing
        // OAuth, the deep-link arrives via onCreate() instead of onNewIntent().
        handleOAuthIntent(intent)
    }

    // ── Flask server ────────────────────────────────────────────────

    private fun showWebView() {
        runOnUiThread {
            splashView.visibility = View.GONE
            webView.visibility = View.VISIBLE
            webView.loadUrl(FLASK_URL)
        }
    }

    private fun startFlaskServer() {
        // Start Python if not already started
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }

        // Set the environment variable via Python so config.py can resolve
        // the Android-appropriate storage directory via os.environ.
        val py = Python.getInstance()
        py.getModule("os").callAttr("environ").callAttr(
            "__setitem__", "SPOTYVIBE_FILES_DIR", filesDir.absolutePath
        )

        // Guard: skip if Flask was already started in this process.
        // Uses a companion-object flag instead of a network call because
        // onCreate() runs on the main thread where Android forbids network I/O.
        if (flaskStarted) {
            Log.i(TAG, "Flask already started, skipping server start")
            showWebView()
            return
        }

        flaskStarted = true

        flaskThread = Thread({
            try {
                Log.i(TAG, "Starting Flask server...")
                val appModule = py.getModule("app")
                val flaskApp = appModule["app"]
                flaskApp?.callAttr(
                    "run",
                    *arrayOf<Any>(),
                    // Keyword arguments via Chaquopy's Kwarg helper
                    com.chaquo.python.Kwarg("host", "127.0.0.1"),
                    com.chaquo.python.Kwarg("port", 5000),
                    com.chaquo.python.Kwarg("debug", false),
                    com.chaquo.python.Kwarg("use_reloader", false)
                )
            } catch (e: Exception) {
                Log.e(TAG, "Flask server error", e)
            }
        }, "flask-server").apply {
            isDaemon = true   // dies when the app process exits
            start()
        }

        // Wait for Flask to be ready, then show the WebView
        Thread({
            waitForFlask()
            showWebView()
        }, "flask-waiter").apply {
            isDaemon = true
            start()
        }
    }

    private fun waitForFlask() {
        for (i in 1..MAX_RETRIES) {
            try {
                val conn = URL(FLASK_URL).openConnection() as HttpURLConnection
                conn.connectTimeout = 400
                conn.readTimeout = 400
                conn.requestMethod = "GET"
                val code = conn.responseCode
                conn.disconnect()
                if (code == 200) {
                    Log.i(TAG, "Flask ready after ${i * RETRY_DELAY_MS}ms")
                    return
                }
            } catch (_: Exception) {
                // Server not ready yet
            }
            Thread.sleep(RETRY_DELAY_MS)
        }
        Log.e(TAG, "Flask did not start within ${MAX_RETRIES * RETRY_DELAY_MS}ms")
    }

    // ── WebView ─────────────────────────────────────────────────────

    private fun configureWebView() {
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true               // for localStorage (theme)
            mediaPlaybackRequiresUserGesture = false
            allowFileAccess = false
            allowContentAccess = false
        }

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(
                view: WebView,
                request: WebResourceRequest
            ): Boolean {
                val url = request.url.toString()
                // Keep localhost traffic inside the WebView
                if (url.startsWith(FLASK_URL)) {
                    return false
                }
                // External URLs (Spotify auth etc.) → system browser
                startActivity(Intent(Intent.ACTION_VIEW, request.url))
                return true
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            // Forward JS console.log to Logcat for debugging
            override fun onConsoleMessage(msg: ConsoleMessage?): Boolean {
                msg?.let {
                    Log.d(TAG, "JS [${it.sourceId()}:${it.lineNumber()}] ${it.message()}")
                }
                return true
            }

            // Handle window.open() popups (e.g. Spotify OAuth)
            // Instead of creating a temporary WebView, intercept the first
            // navigation from the popup and route it appropriately.
            override fun onCreateWindow(
                view: WebView?,
                isDialog: Boolean,
                isUserGesture: Boolean,
                resultMsg: android.os.Message?
            ): Boolean {
                val transport = resultMsg?.obj as? WebView.WebViewTransport ?: return false

                val popupWebView = WebView(this@MainActivity).apply {
                    webViewClient = object : WebViewClient() {
                        override fun shouldOverrideUrlLoading(
                            view: WebView,
                            request: WebResourceRequest
                        ): Boolean {
                            val url = request.url.toString()
                            if (url.startsWith(FLASK_URL)) {
                                // Callback URL — load in the main WebView
                                webView.loadUrl(url)
                            } else {
                                // External URL (Spotify auth page) → system browser
                                startActivity(Intent(Intent.ACTION_VIEW, request.url))
                            }
                            // Clean up immediately after intercepting the URL
                            view.destroy()
                            return true
                        }
                    }
                }
                transport.webView = popupWebView
                resultMsg.sendToTarget()
                return true
            }
        }

        // Enable window.open() support for OAuth popups
        webView.settings.javaScriptCanOpenWindowsAutomatically = true
        webView.settings.setSupportMultipleWindows(true)
    }

    // ── Lifecycle ───────────────────────────────────────────────────

    override fun onDestroy() {
        // Stop the Flask server thread to free resources when the Activity
        // is destroyed.  The thread is a daemon so it will die with the
        // process, but an explicit interrupt avoids lingering sockets while
        // the process is still alive in the background.
        flaskThread?.interrupt()
        flaskThread = null
        webView.destroy()
        super.onDestroy()
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        handleOAuthIntent(intent)
    }

    /**
     * Handle the Spotify OAuth callback via our custom URI scheme.
     * Called from both onNewIntent() (warm resume) and onCreate() (cold start
     * after process death).  Uses Uri.Builder for proper URL encoding.
     */
    private fun handleOAuthIntent(intent: Intent?) {
        intent?.data?.let { uri ->
            if (uri.scheme == "spotyvibe" && uri.host == "callback") {
                val code = uri.getQueryParameter("code")
                if (code != null) {
                    val flaskCallback = Uri.Builder()
                        .scheme("http")
                        .authority("127.0.0.1:5000")
                        .path("/callback")
                        .appendQueryParameter("code", code)
                        .apply {
                            uri.getQueryParameter("state")?.let {
                                appendQueryParameter("state", it)
                            }
                        }
                        .build().toString()
                    Log.i(TAG, "OAuth callback received, forwarding to Flask")
                    webView.loadUrl(flaskCallback)
                } else {
                    // Error case — forward error params to Flask too
                    val error = uri.getQueryParameter("error") ?: "unknown_error"
                    val flaskError = Uri.Builder()
                        .scheme("http")
                        .authority("127.0.0.1:5000")
                        .path("/callback")
                        .appendQueryParameter("error", error)
                        .apply {
                            uri.getQueryParameter("error_description")?.let {
                                appendQueryParameter("error_description", it)
                            }
                        }
                        .build().toString()
                    webView.loadUrl(flaskError)
                }
            }
        }
    }

    private fun registerBackPress() {
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) {
                    webView.goBack()
                } else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })
    }
}
