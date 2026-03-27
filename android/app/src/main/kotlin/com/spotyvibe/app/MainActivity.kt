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
        // Pass the app-internal files directory so config.py can find it
        System.setProperty("SPOTYVIBE_FILES_DIR", filesDir.absolutePath)
        // Also set as env var for os.environ access in Python
        try {
            val env = System.getenv()
            // Android doesn't allow setenv, so pass via system property
            // The Python side reads SPOTYVIBE_FILES_DIR from os.environ
            // which Chaquopy bridges from system properties
        } catch (e: Exception) {
            Log.w(TAG, "Could not set env var, using system property fallback", e)
        }

        // Start Python if not already started
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }

        // Set the environment variable via Python before Flask starts
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
            override fun onCreateWindow(
                view: WebView?,
                isDialog: Boolean,
                isUserGesture: Boolean,
                resultMsg: android.os.Message?
            ): Boolean {
                // Extract the URL from the result message and open in browser
                val transport = resultMsg?.obj as? WebView.WebViewTransport
                if (transport != null) {
                    val tempWebView = WebView(this@MainActivity)
                    tempWebView.webViewClient = object : WebViewClient() {
                        override fun shouldOverrideUrlLoading(
                            view: WebView,
                            request: WebResourceRequest
                        ): Boolean {
                            val url = request.url.toString()
                            if (url.startsWith(FLASK_URL)) {
                                // Callback URL — load in the main WebView
                                webView.loadUrl(url)
                            } else {
                                // External URL — open in system browser
                                startActivity(Intent(Intent.ACTION_VIEW, request.url))
                            }
                            tempWebView.destroy()
                            return true
                        }
                    }
                    transport.webView = tempWebView
                    resultMsg.sendToTarget()
                    return true
                }
                return false
            }
        }

        // Enable window.open() support for OAuth popups
        webView.settings.javaScriptCanOpenWindowsAutomatically = true
        webView.settings.setSupportMultipleWindows(true)
    }

    // ── Lifecycle ───────────────────────────────────────────────────

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
