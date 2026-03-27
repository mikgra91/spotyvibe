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
        startFlaskServer()
    }

    // ── Flask server ────────────────────────────────────────────────

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
            runOnUiThread {
                splashView.visibility = View.GONE
                webView.visibility = View.VISIBLE
                webView.loadUrl(FLASK_URL)
            }
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
        // Handle the Spotify OAuth callback deep-link coming back from the
        // system browser.  When the browser navigates to the redirect URI
        // (http://127.0.0.1:5000/callback?code=...) and the WebView picks
        // it up, reload the main page so the UI refreshes auth status.
        intent?.data?.toString()?.let { url ->
            if (url.startsWith(FLASK_URL)) {
                webView.loadUrl(url)
            }
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            @Suppress("DEPRECATION")
            super.onBackPressed()
        }
    }
}
