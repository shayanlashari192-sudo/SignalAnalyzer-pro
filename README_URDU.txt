SIGNAL ANALYZER PRO — SINGLE PROJECT
===================================

Yeh aapki pehli ZIP (SignalAnalyzer_TestProject) ka upgraded single-project version hai.
Doosri ZIP ka code is project mein merge/use nahi kiya gaya. ZIP ke andar rakhi nested
signal-pro-server.zip ko bhi include nahi kiya gaya.

IMPORTANT: Yeh source project hai, ready-made APK nahi. Is environment mein Android SDK
available nahi, is liye APK yahan compile/test nahi hua. Included GitHub Actions workflow
cloud par debug APK build karta hai; laptop par Android Studio/3GB SDK download zaroori nahi.

FEATURES
--------
- Exness MT5 terminal se real broker quotes aur candles.
- Broker ke tradable symbols automatic discover; visible Market Watch instruments first.
- Forex, Metals, Crypto, Indices, Stocks, Energies aur Other categories (broker symbols ki
  naming/path ke mutabiq best-effort classification).
- Default maximum 250 instruments; Windows bridge mein MAX_SYMBOLS environment variable se
  1000 tak set kar sakte hain. Broker jitne instruments deta hai sirf wohi scan honge.
- M5, M15, H1, H4 analysis; har timeframe ke liye higher-timeframe confirmation:
  M5->M15, M15->H1, H1->H4, H4->D1.
- Six-condition technical confluence: EMA20/EMA50, price vs EMA20, RSI, MACD histogram,
  higher-timeframe EMA trend, ADX trend strength. BUY/SELL tabhi jab 6 mein se kam az kam
  5 conditions align hon; warna WAIT.
- ATR-based indicative Stop Loss (1.5 ATR) and Take Profit (2R). These are analytical levels,
  not guaranteed execution prices or financial advice.
- Current forming candle excluded from signal calculation to reduce repainting.
- Stale quote (>180 seconds) par app WAIT dikhati hai; stale quote par fresh signal nahi banta.
- SQLite database mein candles aur signals permanently save; Android refresh se history delete nahi hoti.
- Signal outcome tracking: later stored candles se TP/SL check; agar same candle mein dono levels
  touch hon to conservative assumption ke taur par SL pehle count hota hai.
- Android app mein PIN lock, server URL setting, category/timeframe selection, market scanner,
  saved signal history, saved candle history aur database summary.
- 15-second app refresh; manual scan option.

REAL-WORLD LIMITATIONS
----------------------
1. Data MT5 terminal ke logged-in broker account se aata hai. PC/VPS par MT5 aur Python bridge
   online hona chahiye. Phone aur PC same trusted Wi-Fi par hon, ya secured HTTPS VPS use karein.
2. App all-world exchanges ka universal feed nahi hai. Sirf aapke Exness/connected MT5 server ke
   available tradable instruments scan honge. Har asset class/stock/crypto har account/region par
   available hona zaroori nahi.
3. Symbols automatically discover hote hain; maximum default 250. Zyada scan karne ke liye
   Windows Command Prompt mein server start karne se pehle run karein: set MAX_SYMBOLS=500
   Phir usi Command Prompt mein Uvicorn start karein.
4. Candles/signals server PC/VPS ki SQLite database mein store hote hain, phone mein nahi.
   Database file: mt5_bridge/market_history.sqlite. Is file ka backup rakhein.
5. Data collection occurs when the app scans the bridge. If the app is closed, the database keeps
   its existing records; when reopened, latest available broker candles are fetched and saved.
6. No guaranteed accuracy, no fabricated quotes, and no automatic trade execution. 5/6 score is
   a technical confluence score, NOT a 83% win probability. Backtest and forward-test on demo.
7. Bridge API has no login/authentication. Keep it on a trusted private LAN only. Do NOT expose
   port 8765 directly to the public internet or port-forward it. Remote access requires HTTPS,
   authentication and firewall/security setup on a properly configured VPS.
8. This Android workflow produces a DEBUG APK for testing, not a signed Play Store release.

WINDOWS MT5 BRIDGE SETUP
------------------------
1. Windows PC par MetaTrader 5 install karein aur Exness DEMO account login karein.
2. MT5 Market Watch mein woh instruments visible karein jinhein scan karna hai. Broker ke
   available tradable instruments auto-discover bhi honge; visible instruments priority par hain.
3. Python 3.12 (64-bit) install karein.
4. Project ke mt5_bridge folder mein jayein aur START_MT5_BRIDGE.bat par double-click karein.
   Ya Command Prompt se chalayein:
     py -3.12 -m pip install -r requirements.txt
     py -3.12 -m uvicorn server:app --host 0.0.0.0 --port 8765
5. Windows Firewall prompt aaye to sirf Private network par Python access allow karein.
6. Command Prompt mein ipconfig run karein aur PC ka IPv4 address note karein, e.g. 192.168.1.10.
7. Phone aur PC ko same trusted Wi-Fi par connect karein. App ke Connection / Server Settings mein:
     http://192.168.1.10:8765
   enter karein.
8. Bridge chalane ke liye MT5 terminal open aur logged in rehna chahiye.

APK BUILD — ANDROID STUDIO KE BAGHAIR
------------------------------------
1. https://github.com par sign in/create account karein.
2. New repository create karein (private repository recommended).
3. Is ZIP ko extract karein aur extracted folder ke ANDAR ka tamam content repository mein upload
   karein. .github folder zaroor upload ho; GitHub web uploader mein hidden folders visible hon.
4. Repository ke Actions tab mein "Build Android APK" workflow select karein.
5. "Run workflow" press karein. Build successful hone ka wait karein.
6. Workflow run ke Artifacts section se "SignalAnalyzer-debug-apk" download karein.
7. Artifact ZIP extract karein; app-debug.apk Android phone mein transfer/install karein.
8. Android security prompt aaye to us file manager/browser ke liye "Install unknown apps" allow karein.
9. App open karein, PIN set karein, Connection / Server Settings mein Windows PC ka bridge URL save karein.
10. Scan All Available Markets press karein.

TROUBLESHOOTING
---------------
- Bridge unavailable: PC aur phone same Wi-Fi, correct IPv4, firewall private access, MT5 logged in.
- MT5 not connected: MT5 terminal khol kar account login aur Algo/terminal connectivity check karein.
- No instruments: Market Watch mein symbols show karein; broker account ki trading permissions check karein.
- Data unavailable: market closed, symbol unsupported, or MT5 history not downloaded. MT5 chart khol kar
  history load karein, phir scan karein.
- APK build failed: GitHub Actions build log ka error check karein; repository mein android/ aur .github/
  workflows/android-apk.yml folders root par hon.
