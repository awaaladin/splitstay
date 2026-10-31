package com.splitpay.app

import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.os.Bundle
import android.print.PrintManager
import android.view.View
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ProgressBar
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import java.net.URISyntaxException

private const val START_PATH = "/dashboard/"

/** Shows the SplitPay website itself, so every screen and feature is the website's, and adds what only an app can. */
class MainActivity : ComponentActivity() {
    private lateinit var web: WebView
    private lateinit var refresh: SwipeRefreshLayout
    private lateinit var progress: ProgressBar
    private lateinit var offline: LinearLayout
    private val siteHost: String = Uri.parse(BuildConfig.SITE_URL).host.orEmpty()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        WindowCompat.getInsetsController(window, window.decorView).isAppearanceLightStatusBars = false
        setContentView(R.layout.activity_main)

        val root = findViewById<View>(R.id.root)
        web = findViewById(R.id.web)
        refresh = findViewById(R.id.refresh)
        progress = findViewById(R.id.progress)
        offline = findViewById(R.id.offline)

        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            val keyboard = insets.getInsets(WindowInsetsCompat.Type.ime())
            view.setPadding(bars.left, bars.top, bars.right, maxOf(bars.bottom, keyboard.bottom))
            WindowInsetsCompat.CONSUMED
        }

        configureWeb()
        refresh.setColorSchemeResources(R.color.navy)
        refresh.setOnRefreshListener { web.reload() }
        findViewById<Button>(R.id.retry).setOnClickListener { retry() }
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (web.canGoBack()) web.goBack() else finish()
            }
        })

        if (savedInstanceState != null) web.restoreState(savedInstanceState) else web.loadUrl(BuildConfig.SITE_URL + START_PATH)
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun configureWeb() {
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = false
            userAgentString = "$userAgentString SplitPayAndroid/${BuildConfig.VERSION_NAME}"
        }
        web.addJavascriptInterface(Bridge(), "SplitPayApp")
        web.webViewClient = Client()
        web.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView, percent: Int) {
                progress.progress = percent
                progress.visibility = if (percent < 100) View.VISIBLE else View.GONE
            }
        }
        web.setDownloadListener { url, _, _, _, _ -> openOutside(Uri.parse(url)) }
    }

    private fun onOurSite(url: String?): Boolean = url != null && Uri.parse(url).host == siteHost

    private fun retry() {
        offline.visibility = View.GONE
        if (web.url == null) web.loadUrl(BuildConfig.SITE_URL + START_PATH) else web.reload()
    }

    private fun openOutside(uri: Uri): Boolean = try {
        startActivity(Intent(Intent.ACTION_VIEW, uri))
        true
    } catch (e: ActivityNotFoundException) {
        false
    }

    /** Bank apps and USSD links arrive as intent: URLs. Only their target app or web fallback is ever opened. */
    private fun openIntentUrl(view: WebView, url: String) {
        val intent = try {
            Intent.parseUri(url, Intent.URI_INTENT_SCHEME)
        } catch (e: URISyntaxException) {
            return
        }
        intent.addCategory(Intent.CATEGORY_BROWSABLE)
        intent.component = null
        intent.selector = null
        try {
            startActivity(intent)
        } catch (e: ActivityNotFoundException) {
            intent.getStringExtra("browser_fallback_url")?.let(view::loadUrl)
        }
    }

    private inner class Client : WebViewClient() {
        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
            val uri = request.url
            return when (uri.scheme) {
                "https" -> false // Includes Paystack and the banks' card checks, which must stay in this session.
                "splitpay" -> {
                    view.loadUrl(BuildConfig.SITE_URL + START_PATH)
                    true
                }
                "intent" -> {
                    openIntentUrl(view, uri.toString())
                    true
                }
                else -> {
                    openOutside(uri)
                    true
                }
            }
        }

        override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) {
            refresh.isEnabled = onOurSite(url) // Pulling down must not reload a card payment in progress.
        }

        override fun onPageFinished(view: WebView, url: String?) {
            refresh.isRefreshing = false
            if (onOurSite(url)) view.evaluateJavascript(PAGE_BRIDGE, null)
        }

        override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
            if (request.isForMainFrame) {
                refresh.isRefreshing = false
                offline.visibility = View.VISIBLE
            }
        }
    }

    /** What the website's Print and Copy token buttons need, which a WebView doesn't provide. */
    private inner class Bridge {
        @JavascriptInterface
        fun print() = runOnUiThread {
            if (onOurSite(web.url)) {
                val manager = getSystemService(PRINT_SERVICE) as PrintManager
                manager.print("SplitPay receipt", web.createPrintDocumentAdapter("SplitPay receipt"), null)
            }
        }

        @JavascriptInterface
        fun copy(text: String) = runOnUiThread {
            if (onOurSite(web.url)) {
                val manager = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
                manager.setPrimaryClip(ClipData.newPlainText("SplitPay", text))
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        if (intent.data?.scheme == "splitpay") web.loadUrl(BuildConfig.SITE_URL + START_PATH)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        web.saveState(outState)
    }

    private companion object {
        val PAGE_BRIDGE = """
            window.print = function () { SplitPayApp.print(); };
            if (navigator.clipboard) {
              navigator.clipboard.writeText = function (text) { SplitPayApp.copy(text); return Promise.resolve(); };
            }
        """.trimIndent()
    }
}
