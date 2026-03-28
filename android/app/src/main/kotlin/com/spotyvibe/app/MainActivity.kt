package com.spotyvibe.app

import android.app.DownloadManager
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.util.Log
import android.view.View
import android.webkit.ConsoleMessage
import android.webkit.ValueCallback
import android.webkit.URLUtil
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.net.HttpURLConnection
import java.net.URL

class MainActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "SpotyVibe"
        private const val FLASK_URL = "http://127.0.0.1:5000"
        private const val ONBOARDING_URL = "$FLASK_URL/onboarding"
        private const val MAX_RETRIES = 60          // up to 30 seconds
        private const val RETRY_DELAY_MS = 500L
        @Volatile private var flaskStarted = false  // survives Activity re-creation
    }

    private lateinit var webView: WebView
    private lateinit var splashView: View
    private lateinit var errorView: View
    private var flaskThread: Thread? = null

    // File input handler for <input type="file"> in the WebView.
    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null
    private val fileChooserLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        val callback = fileChooserCallback ?: return@registerForActivityResult
        fileChooserCallback = null

        if (result.resultCode != RESULT_OK) {
            callback.onReceiveValue(null)
            return@registerForActivityResult
        }

        val data = result.data
        val uris = mutableListOf<Uri>()
        data?.data?.let { uris.add(it) }
        data?.clipData?.let { clip ->
            for (i in 0 until clip.itemCount) {
                uris.add(clip.getItemAt(i).uri)
            }
        }

        callback.onReceiveValue(if (uris.isNotEmpty()) uris.toTypedArray() else null)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        splashView = findViewById(R.id.splashView)
        webView = findViewById(R.id.webView)
        errorView = findViewById(R.id.errorView)

        // Retry button in the error view
        findViewById<View>(R.id.retryButton).setOnClickListener {
            retryFlaskServer()
        }

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
            errorView.visibility = View.GONE
            webView.visibility = View.VISIBLE
            webView.loadUrl(ONBOARDING_URL)
        }
    }

    private fun showError() {
        runOnUiThread {
            splashView.visibility = View.GONE
            webView.visibility = View.GONE
            errorView.visibility = View.VISIBLE
        }
    }

    private fun startFlaskServer() {
        // Start Python if not already started
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }

        val py = Python.getInstance()

        // Guard: skip if Flask was already started in this process.
        if (flaskStarted) {
            Log.i(TAG, "Flask already started, skipping server start")
            showWebView()
            return
        }

        flaskStarted = true

        flaskThread = Thread({
            try {
                Log.i(TAG, "Starting Flask server...")
                py.getModule("spotyvibe_bootstrap").callAttr("start", filesDir.absolutePath)
            } catch (e: Exception) {
                Log.e(TAG, "Flask server error", e)
            }
        }, "flask-server").apply {
            isDaemon = true   // dies when the app process exits
            start()
        }

        // Wait for Flask to be ready, then show the WebView (or error)
        Thread({
            if (waitForFlask()) {
                showWebView()
            } else {
                showError()
            }
        }, "flask-waiter").apply {
            isDaemon = true
            start()
        }
    }

    private fun waitForFlask(): Boolean {
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
                    return true
                }
            } catch (_: Exception) {
                // Server not ready yet
            }
            Thread.sleep(RETRY_DELAY_MS)
        }
        Log.e(TAG, "Flask did not start within ${MAX_RETRIES * RETRY_DELAY_MS}ms")
        return false
    }

    // ── WebView ─────────────────────────────────────────────────────

    private fun retryFlaskServer() {
        // Show splash again and re-attempt starting Flask
        runOnUiThread {
            errorView.visibility = View.GONE
            splashView.visibility = View.VISIBLE
        }
        flaskStarted = false
        startFlaskServer()
    }

    private fun configureWebView() {
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true               // for localStorage (theme)
            mediaPlaybackRequiresUserGesture = false
            allowFileAccess = false
            // Required for Android's Storage Access Framework (content:// URIs)
            // when using <input type="file"> in the WebView.
            allowContentAccess = true
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
            override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: WebChromeClient.FileChooserParams?
            ): Boolean {
                // Cancel any pending chooser.
                this@MainActivity.fileChooserCallback?.onReceiveValue(null)
                this@MainActivity.fileChooserCallback = filePathCallback

                val intent = Intent(Intent.ACTION_GET_CONTENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "*/*"
                    putExtra(
                        Intent.EXTRA_MIME_TYPES,
                        arrayOf("application/json", "text/json", "text/plain")
                    )
                }

                return try {
                    fileChooserLauncher.launch(Intent.createChooser(intent, "Select profile JSON"))
                    true
                } catch (e: Exception) {
                    Log.e(TAG, "File chooser error", e)
                    this@MainActivity.fileChooserCallback = null
                    filePathCallback?.onReceiveValue(null)
                    false
                }
            }

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

                // Handle file downloads (used for exporting the profile JSON).
        // Security: restrict downloads to our trusted localhost export endpoint.
        webView.setDownloadListener { url, userAgent, contentDisposition, mimeType, _ ->
            try {
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

                    val filename = URLUtil.guessFileName(url, contentDisposition, mimeType)
                    setTitle(filename)

                    setNotificationVisibility(
                        DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED
                    )
                    setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, filename)
                }

                val dm = getSystemService(DOWNLOAD_SERVICE) as DownloadManager
                dm.enqueue(request)
            } catch (e: Exception) {
                Log.e(TAG, "Download failed", e)
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
