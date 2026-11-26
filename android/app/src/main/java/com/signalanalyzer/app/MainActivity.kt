package com.signalanalyzer.app

import android.app.Activity
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.view.Gravity
import android.widget.*
import android.graphics.Color
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import kotlin.concurrent.thread

class MainActivity : Activity() {
    private val prefs by lazy { getSharedPreferences("signal_analyzer", MODE_PRIVATE) }
    private val handler = Handler(Looper.getMainLooper())
    private var baseUrl = "http://192.168.1.10:8765"
    private lateinit var root: LinearLayout
    private lateinit var status: TextView
    private lateinit var content: LinearLayout
    private lateinit var timeframe: Spinner
    private lateinit var category: Spinner
    private var polling = false
    private var scanning = false
    private var dashboardReady = false
    private val autoScan = object : Runnable { override fun run() { if (dashboardReady) { refresh(); handler.postDelayed(this, 15000) } } }
    private val bg = Color.rgb(10, 16, 28)
    private val panel = Color.rgb(24, 34, 52)
    private val white = Color.WHITE
    private val muted = Color.LTGRAY

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        baseUrl = prefs.getString("base_url", baseUrl)!!.trimEnd('/')
        if (prefs.getString("pin", null) == null) showPinSetup() else showUnlock()
    }

    private fun shell(title: String) {
        root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(20, 20, 20, 20); setBackgroundColor(bg) }
        val scroller = ScrollView(this)
        scroller.addView(root)
        setContentView(scroller)
        root.addView(TextView(this).apply { text = title; textSize = 23f; setTextColor(white); setPadding(0,0,0,14) })
    }

    private fun button(label: String, action: () -> Unit): Button = Button(this).apply { text = label; setOnClickListener { action() } }
    private fun edit(hintText: String, type: Int = InputType.TYPE_CLASS_TEXT): EditText = EditText(this).apply { hint = hintText; inputType = type; setTextColor(white); setHintTextColor(muted) }

    private fun showPinSetup() {
        shell("SIGNAL ANALYZER")
        val pin = edit("Create 4-8 digit PIN", InputType.TYPE_CLASS_NUMBER_PASSWORD)
        root.addView(pin)
        root.addView(button("Set PIN") {
            val v = pin.text.toString()
            if (v.length !in 4..8) pin.error = "PIN must be 4-8 digits"
            else { prefs.edit().putString("pin", v).apply(); showDashboard() }
        })
    }

    private fun showUnlock() {
        shell("APP LOCK")
        val pin = edit("Enter PIN", InputType.TYPE_CLASS_NUMBER_PASSWORD)
        root.addView(pin)
        root.addView(button("Unlock") {
            if (pin.text.toString() == prefs.getString("pin", "")) showDashboard() else pin.error = "Incorrect PIN"
        })
    }

    private fun showDashboard() {
        dashboardReady = true
        shell("SIGNAL ANALYZER PRO")
        status = TextView(this).apply { text = "Waiting for MT5 bridge…"; setTextColor(muted); textSize = 13f }
        root.addView(status)
        root.addView(button("Connection / Server Settings") { showSettings() })
        timeframe = Spinner(this).apply { adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_dropdown_item, listOf("M5", "M15", "H1", "H4")) }
        root.addView(label("TIMEFRAME")); root.addView(timeframe)
        category = Spinner(this).apply { adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_dropdown_item, listOf("ALL", "FOREX", "METALS", "CRYPTO", "INDICES", "STOCKS", "ENERGIES", "OTHER")) }
        root.addView(label("MARKET CATEGORY")); root.addView(category)
        root.addView(button("SCAN ALL AVAILABLE MARKETS") { refresh() })
        root.addView(button("Saved Signal History") { loadHistory() })
        root.addView(button("Saved Data Summary") { loadSummary() })
        content = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(content)
        refresh()
        handler.removeCallbacks(autoScan)
        handler.postDelayed(autoScan, 15000)
    }

    private fun label(s: String) = TextView(this).apply { text = s; textSize = 11f; setTextColor(Color.rgb(120, 180, 220)); setPadding(0, 12, 0, 2) }

    private fun showSettings() {
        shell("SERVER CONNECTION")
        val url = edit("http://192.168.1.10:8765").apply { setText(baseUrl) }
        root.addView(TextView(this).apply { text = "Enter the LAN/VPS address where the MT5 Python bridge is running. Example: http://192.168.1.10:8765"; setTextColor(muted) })
        root.addView(url)
        root.addView(button("Save server address") {
            val v = url.text.toString().trim().trimEnd('/')
            if (!v.startsWith("http://") && !v.startsWith("https://")) url.error = "Enter a valid http:// or https:// address"
            else { baseUrl = v; prefs.edit().putString("base_url", baseUrl).apply(); showDashboard() }
        })
        root.addView(button("Back") { showDashboard() })
    }

    private fun request(path: String, done: (JSONObject?, String?) -> Unit) {
        thread {
            var conn: HttpURLConnection? = null
            try {
                conn = URL(baseUrl + path).openConnection() as HttpURLConnection
                conn.connectTimeout = 7000; conn.readTimeout = 90000; conn.requestMethod = "GET"
                val code = conn.responseCode
                val stream = if (code in 200..299) conn.inputStream else conn.errorStream
                val body = stream.bufferedReader().use { it.readText() }
                val obj = JSONObject(body)
                runOnUiThread { done(obj, null) }
            } catch (e: Exception) { runOnUiThread { done(null, e.message ?: "Connection failed") } }
            finally { conn?.disconnect() }
        }
    }

    private fun refresh() {
        if (scanning) return
        scanning = true
        val tf = timeframe.selectedItem.toString()
        val cat = category.selectedItem.toString()
        status.text = "Scanning broker instruments…"
        content.removeAllViews()
        request("/api/markets?tf=$tf&category=$cat&limit=1000") { json, error ->
            scanning = false
            if (error != null || json == null) { status.text = "Bridge unavailable: $error. Check MT5 PC/VPS and server address."; return@request }
            if (!json.optBoolean("connected")) { status.text = "MT5 not connected: ${json.optString("error")}"; return@request }
            val arr = json.optJSONArray("markets") ?: run { status.text = "No market data returned"; return@request }
            status.text = "Connected • ${json.optInt("scanned")} instruments scanned • $tf • Broker feed (quote freshness shown per symbol)"
            for (i in 0 until arr.length()) {
                val m = arr.getJSONObject(i)
                val card = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(14, 12, 14, 12); setBackgroundColor(panel) }
                card.addView(TextView(this).apply { text = "${m.optString("symbol")}  •  ${m.optString("category")}"; textSize = 18f; setTextColor(white) })
                if (!m.optBoolean("available")) {
                    card.addView(TextView(this).apply { text = "DATA UNAVAILABLE: ${m.optString("reason")}"; setTextColor(Color.YELLOW) })
                } else {
                    val fresh = m.optBoolean("quote_fresh", false)
                    val sig = if (fresh) m.optString("signal", "WAIT") else "STALE DATA • WAIT"
                    val sigColor = when (sig) { "BUY" -> Color.rgb(65,220,130); "SELL" -> Color.rgb(255,95,95); else -> Color.YELLOW }
                    card.addView(TextView(this).apply { text = "$sig  •  ${m.optString("score_label")}"; textSize = 19f; setTextColor(sigColor) })
                    card.addView(TextView(this).apply { text = "Quote age: ${m.optInt("quote_age_seconds")} sec • HTF: ${m.optString("higher_timeframe")}"; setTextColor(muted) })
                    card.addView(TextView(this).apply { text = "Bid ${m.optDouble("bid")}   Ask ${m.optDouble("ask")}   Spread ${m.optDouble("spread")}"; setTextColor(muted) })
                    card.addView(TextView(this).apply { text = m.optString("reason"); setTextColor(muted) })
                    if (sig != "WAIT") card.addView(TextView(this).apply { text = "Entry: ${m.optDouble("entry")}   SL: ${m.optDouble("stop_loss")}   TP: ${m.optDouble("take_profit")}"; setTextColor(white) })
                    card.addView(button("View saved candles") { loadCandles(m.optString("symbol"), tf) })
                }
                content.addView(card); content.addView(Space(this).apply { minimumHeight = 10 })
            }
        }
    }

    private fun loadHistory() {
        dashboardReady = false; handler.removeCallbacks(autoScan)
        content.removeAllViews(); status.text = "Loading saved signal history…"
        content.addView(button("Back to scanner") { showDashboard() })
        request("/api/history/signals?limit=200") { json, error ->
            if (error != null || json == null) { status.text = "History unavailable: $error"; return@request }
            val arr = json.optJSONArray("signals") ?: return@request
            status.text = "Permanent signal history • ${arr.length()} records"
            for (i in 0 until arr.length()) {
                val s = arr.getJSONObject(i)
                val t = TextView(this).apply {
                    text = "${s.optString("symbol")} ${s.optString("timeframe")} • ${s.optString("side")}\nEntry ${s.optDouble("entry")} | SL ${s.optDouble("stop_loss")} | TP ${s.optDouble("take_profit")}\n${s.optString("reason")}\nOutcome: ${s.optString("outcome")}"
                    setTextColor(white); setPadding(12,10,12,10); setBackgroundColor(panel)
                }
                content.addView(t); content.addView(Space(this).apply { minimumHeight = 8 })
            }
        }
    }

    private fun loadCandles(symbol: String, tf: String) {
        dashboardReady = false; handler.removeCallbacks(autoScan)
        content.removeAllViews(); status.text = "Loading stored candles for $symbol…"
        content.addView(button("Back to scanner") { showDashboard() })
        request("/api/history/candles?symbol=${URLEncoder.encode(symbol, "UTF-8")}&tf=$tf&limit=300") { json, error ->
            if (error != null || json == null) { status.text = "Candle history unavailable: $error"; return@request }
            val arr = json.optJSONArray("candles") ?: return@request
            status.text = "${json.optInt("count")} saved candles • $symbol • $tf"
            for (i in arr.length()-1 downTo 0) {
                val c = arr.getJSONObject(i)
                content.addView(TextView(this).apply {
                    text = "${c.optLong("time")}   O ${c.optDouble("open")}  H ${c.optDouble("high")}  L ${c.optDouble("low")}  C ${c.optDouble("close")}"
                    setTextColor(white); setPadding(8,6,8,6)
                })
            }
        }
    }

    private fun loadSummary() {
        dashboardReady = false; handler.removeCallbacks(autoScan)
        content.removeAllViews()
        content.addView(button("Back to scanner") { showDashboard() })
        request("/api/history/summary") { json, error ->
            if (error != null || json == null) { status.text = "Summary unavailable: $error"; return@request }
            status.text = "Saved permanently on MT5 server • Candles: ${json.optInt("candles_saved")} • Signals: ${json.optInt("signals_saved")}"
        }
    }

    override fun onResume() {
        super.onResume()
        if (dashboardReady) handler.postDelayed(autoScan, 15000)
    }

    override fun onPause() {
        handler.removeCallbacks(autoScan)
        super.onPause()
    }
}
