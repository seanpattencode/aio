package com.aios.a
import android.app.Activity
import android.os.Bundle
import android.webkit.WebView
import android.webkit.WebViewClient

private const val ERR = "<body style='font:20px monospace;padding:40px;background:#1a1a1a;color:#0f0'>" +
    "<h2>a ui not running</h2>In Termux run: <b>a ui on</b><br><br>" +
    "<button onclick='location=\"http://localhost:1111\"' style='font-size:20px;padding:12px 24px'>Retry</button>"

class MainActivity : Activity() {
    private lateinit var wv: WebView
    @Suppress("DEPRECATION")
    override fun onBackPressed() { if (wv.canGoBack()) wv.goBack() else super.onBackPressed() }
    override fun onCreate(b: Bundle?) {
        super.onCreate(b)
        wv = WebView(this).apply {
            settings.javaScriptEnabled = true
            webViewClient = object : WebViewClient() {
                @Suppress("DEPRECATION")
                override fun onReceivedError(v: WebView, c: Int, d: String?, u: String?) {
                    v.loadData(ERR, "text/html", "utf-8")
                }
            }
            loadUrl("http://localhost:1111")
        }
        setContentView(wv)
    }
}
