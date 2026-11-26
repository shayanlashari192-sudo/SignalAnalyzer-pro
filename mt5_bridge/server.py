"""Signal Analyzer MT5 bridge.
Reads real quotes and closed candles from the logged-in MetaTrader 5 terminal.
Persists candle and signal history in SQLite. No synthetic prices or signals.
"""
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import MetaTrader5 as mt5
import sqlite3, time, hashlib, os
from datetime import datetime, timezone

app = FastAPI(title="Signal Analyzer - MT5 Multi-Market Bridge", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# MT5 symbols are discovered from the connected broker at runtime.
# Optional allow-list can be supplied as comma-separated MT5 symbol names in SYMBOL_ALLOWLIST.
ALLOWLIST = {x.strip().upper() for x in os.getenv("SYMBOL_ALLOWLIST", "").split(",") if x.strip()}
MAX_SYMBOLS = max(1, min(int(os.getenv("MAX_SYMBOLS", "250")), 1000))
DB = os.getenv("SIGNAL_DB", os.path.join(os.path.dirname(__file__), "market_history.sqlite"))
TIMEFRAMES = {"M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4}
HIGHER_TIMEFRAMES = {"M5": mt5.TIMEFRAME_M15, "M15": mt5.TIMEFRAME_H1, "H1": mt5.TIMEFRAME_H4, "H4": mt5.TIMEFRAME_D1}


def db():
    c = sqlite3.connect(DB, timeout=20)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("""CREATE TABLE IF NOT EXISTS candles (
      symbol TEXT NOT NULL, tf TEXT NOT NULL, time INTEGER NOT NULL,
      open REAL, high REAL, low REAL, close REAL, tick_volume INTEGER DEFAULT 0,
      PRIMARY KEY(symbol,tf,time))""")
    c.execute("""CREATE TABLE IF NOT EXISTS signals (
      id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, tf TEXT NOT NULL,
      candle_time INTEGER NOT NULL, generated_at INTEGER NOT NULL, side TEXT NOT NULL,
      entry REAL, stop_loss REAL, take_profit REAL, score INTEGER, reason TEXT,
      outcome TEXT DEFAULT 'OPEN', UNIQUE(symbol,tf,candle_time))""")
    c.commit()
    return c


def connect():
    if mt5.initialize():
        return True, None
    return False, mt5.last_error()


def classify(name, path=""):
    """Best-effort broker-symbol grouping; broker path is used as an extra clue."""
    n = name.upper()
    p = path.upper()
    s = n + " " + p
    if any(x in s for x in ("BTC", "ETH", "XRP", "LTC", "SOL", "ADA", "DOGE", "CRYPTO")): return "CRYPTO"
    if any(x in s for x in ("XAU", "XAG", "GOLD", "SILVER", "PLATINUM", "PALLADIUM")): return "METALS"
    if any(x in s for x in ("OIL", "BRENT", "WTI", "NGAS", "NATGAS", "ENERGY")): return "ENERGIES"
    if any(x in s for x in ("US30", "US500", "USTEC", "US100", "NAS", "SPX", "SP500", "DAX", "GER", "UK100", "JP225", "INDEX")): return "INDICES"
    if any(x in s for x in ("STOCK", "SHARES", "EQUITIES", "NYSE", "NASDAQ", "AMEX")) or n in {"AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOG", "META"}: return "STOCKS"
    currencies = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "SGD", "HKD", "NOK", "SEK", "PLN", "TRY", "ZAR", "MXN", "CNH", "CNY"}
    prefix = "".join(ch for ch in n[:6] if ch.isalpha())
    if len(prefix) == 6 and prefix[:3] in currencies and prefix[3:] in currencies: return "FOREX"
    if "FOREX" in p or "CURRENCIES" in p: return "FOREX"
    return "OTHER"


def get_symbols():
    all_symbols = mt5.symbols_get()
    if all_symbols is None: return []
    candidates = []
    for item in all_symbols:
        name = item.name
        if ALLOWLIST and name.upper() not in ALLOWLIST:
            continue
        info = mt5.symbol_info(name)
        if info is None or getattr(info, "trade_mode", 0) == 0:
            continue
        candidates.append({"symbol": name, "category": classify(name, getattr(item, "path", "")),
                           "description": getattr(item, "description", ""),
                           "visible": bool(getattr(info, "visible", False))})
    candidates.sort(key=lambda x: (not x["visible"], x["category"], x["symbol"]))
    return candidates[:MAX_SYMBOLS]


def ema(values, period):
    if len(values) < period: return None
    k = 2 / (period + 1)
    out = sum(values[:period]) / period
    for x in values[period:]: out = x * k + out * (1-k)
    return out


def rsi(values, period=14):
    if len(values) < period + 1: return None
    changes = [values[i] - values[i-1] for i in range(len(values)-period, len(values))]
    gains = sum(max(x, 0) for x in changes) / period
    losses = sum(max(-x, 0) for x in changes) / period
    if losses == 0: return 50.0 if gains == 0 else 100.0
    return 100 - 100 / (1 + gains/losses)


def atr(rates, period=14):
    if len(rates) < period + 1: return None
    tr = []
    for i in range(len(rates)-period, len(rates)):
        hi, lo, prev = float(rates[i]['high']), float(rates[i]['low']), float(rates[i-1]['close'])
        tr.append(max(hi-lo, abs(hi-prev), abs(lo-prev)))
    return sum(tr)/len(tr)


def ema_series(values, period):
    if len(values) < period: return []
    alpha = 2 / (period + 1)
    current = sum(values[:period]) / period
    out = [None] * (period - 1) + [current]
    for value in values[period:]:
        current = value * alpha + current * (1 - alpha)
        out.append(current)
    return out


def macd_histogram(values):
    if len(values) < 35: return None
    fast, slow = ema_series(values, 12), ema_series(values, 26)
    macd_values = [fast[i] - slow[i] for i in range(25, len(values))]
    signal = ema(macd_values, 9)
    return macd_values[-1] - signal if signal is not None else None


def adx_value(rates, period=14):
    if len(rates) < period * 2 + 1: return None
    dx_values = []
    for end in range(len(rates) - period, len(rates)):
        plus_dm, minus_dm, trs = [], [], []
        for i in range(end - period + 1, end + 1):
            up = float(rates[i]['high']) - float(rates[i-1]['high'])
            down = float(rates[i-1]['low']) - float(rates[i]['low'])
            plus_dm.append(up if up > down and up > 0 else 0.0)
            minus_dm.append(down if down > up and down > 0 else 0.0)
            hi, lo, prev = float(rates[i]['high']), float(rates[i]['low']), float(rates[i-1]['close'])
            trs.append(max(hi-lo, abs(hi-prev), abs(lo-prev)))
        tr_sum = sum(trs)
        if tr_sum <= 0: continue
        pdi, mdi = 100 * sum(plus_dm) / tr_sum, 100 * sum(minus_dm) / tr_sum
        if pdi + mdi > 0: dx_values.append(100 * abs(pdi-mdi) / (pdi+mdi))
    return sum(dx_values)/len(dx_values) if dx_values else None


def update_signal_outcomes(c, symbol, tf):
    """Resolve stored signals against later real candles; if SL and TP hit in one bar, count SL first."""
    open_rows = c.execute("SELECT id,side,stop_loss,take_profit,candle_time FROM signals WHERE symbol=? AND tf=? AND outcome='OPEN'", (symbol,tf)).fetchall()
    for sid, side, sl, tp, signal_time in open_rows:
        bars = c.execute("SELECT time,high,low FROM candles WHERE symbol=? AND tf=? AND time>? ORDER BY time", (symbol,tf,signal_time)).fetchall()
        outcome = None
        for _, high, low in bars:
            if side == 'BUY':
                hit_sl = sl is not None and low <= sl
                hit_tp = tp is not None and high >= tp
            else:
                hit_sl = sl is not None and high >= sl
                hit_tp = tp is not None and low <= tp
            if hit_sl:
                outcome = 'SL'
                break
            if hit_tp:
                outcome = 'TP'
                break
        if outcome:
            c.execute("UPDATE signals SET outcome=? WHERE id=?", (outcome,sid))


def analyze(rates, higher_rates):
    closes = [float(x['close']) for x in rates]
    htf_closes = [float(x['close']) for x in higher_rates]
    e20, e50, rv, av = ema(closes,20), ema(closes,50), rsi(closes), atr(rates)
    mh, adx = macd_histogram(closes), adx_value(rates)
    he20, he50 = ema(htf_closes,20), ema(htf_closes,50)
    if None in (e20,e50,rv,av,mh,adx,he20,he50) or av <= 0:
        return {"signal":"WAIT", "score":0, "max_score":6, "reason":"Not enough current and higher-timeframe history", "atr":av}
    last = closes[-1]
    bull_checks = [e20 > e50, last > e20, 50 < rv < 70, mh > 0, he20 > he50, adx >= 18]
    bear_checks = [e20 < e50, last < e20, 30 < rv < 50, mh < 0, he20 < he50, adx >= 18]
    bull, bear = sum(bull_checks), sum(bear_checks)
    if bull >= 5 and bull > bear:
        side, score = "BUY", bull
        reason = "Bullish confluence: EMA trend, price position, RSI, MACD, higher-timeframe trend and ADX strength"
    elif bear >= 5 and bear > bull:
        side, score = "SELL", bear
        reason = "Bearish confluence: EMA trend, price position, RSI, MACD, higher-timeframe trend and ADX strength"
    else:
        side, score = "WAIT", max(bull,bear)
        reason = "No 5/6 confluence: wait for trend, momentum and higher-timeframe confirmation"
    return {"signal":side, "score":score, "max_score":6, "reason":reason, "atr":av,
            "rsi":round(rv,2), "adx":round(adx,2), "macd_histogram":mh}


@app.get("/api/status")
def status():
    ok, err = connect()
    if not ok: return {"connected":False, "error":str(err)}
    info = mt5.terminal_info()
    return {"connected":bool(info and info.connected), "terminal_connected":bool(info and info.connected),
            "server_time":datetime.now(timezone.utc).isoformat(), "broker":getattr(mt5.account_info(), 'server', None)}


@app.get("/api/symbols")
def symbols():
    ok, err = connect()
    if not ok: return {"connected":False, "error":str(err), "symbols":[]}
    items = get_symbols()
    return {"connected":True, "count":len(items), "symbols":items, "note":"Tradable broker symbols are discovered automatically; visible Market Watch instruments are prioritized. Scan is capped by MAX_SYMBOLS."}


@app.get("/api/markets")
def markets(tf: str = "M15", category: str = "ALL", limit: int = Query(250, ge=1, le=1000)):
    if tf not in TIMEFRAMES: return {"connected":False, "error":"Unsupported timeframe", "markets":[]}
    ok, err = connect()
    if not ok: return {"connected":False, "error":str(err), "markets":[]}
    selected = get_symbols()
    if category.upper() != "ALL": selected = [x for x in selected if x['category'] == category.upper()]
    selected = selected[:min(limit, MAX_SYMBOLS)]
    out=[]; c=db()
    for item in selected:
        symbol, cat = item['symbol'], item['category']
        if not mt5.symbol_select(symbol, True):
            out.append({"symbol":symbol,"category":cat,"available":False,"reason":"Broker did not enable this symbol"}); continue
        tick = mt5.symbol_info_tick(symbol)
        rates = mt5.copy_rates_from_pos(symbol, TIMEFRAMES[tf], 0, 502)
        higher_rates = mt5.copy_rates_from_pos(symbol, HIGHER_TIMEFRAMES[tf], 0, 180)
        # Exclude the currently-forming candles to avoid repainting signals.
        if tick is None or rates is None or higher_rates is None or len(rates) < 100 or len(higher_rates) < 65:
            out.append({"symbol":symbol,"category":cat,"available":False,"reason":"Live quote or sufficient candle history unavailable"}); continue
        closed = rates[:-1]
        rows=[]
        for r in closed:
            rows.append((symbol,tf,int(r['time']),float(r['open']),float(r['high']),float(r['low']),float(r['close']),int(r['tick_volume'])))
        c.executemany("INSERT OR REPLACE INTO candles(symbol,tf,time,open,high,low,close,tick_volume) VALUES (?,?,?,?,?,?,?,?)", rows)
        a=analyze(closed, higher_rates[:-1])
        quote_age = max(0, int(time.time()) - int(tick.time))
        if quote_age > 180:
            a = {"signal":"WAIT", "score":0, "max_score":6,
                 "reason":f"Broker quote is stale ({quote_age}s old); no fresh signal generated", "atr":a.get("atr")}
        last=closed[-1]; entry=float(tick.ask if a['signal']=='BUY' else tick.bid)
        sl=tp=None
        if a['signal'] in ('BUY','SELL') and a['atr']:
            risk=1.5*a['atr']; sl=entry-risk if a['signal']=='BUY' else entry+risk
            tp=entry+2*risk if a['signal']=='BUY' else entry-2*risk
        if a['signal'] in ('BUY','SELL'):
            c.execute("INSERT OR IGNORE INTO signals(symbol,tf,candle_time,generated_at,side,entry,stop_loss,take_profit,score,reason) VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (symbol,tf,int(last['time']),int(time.time()),a['signal'],entry,sl,tp,a['score'],a['reason']))
        update_signal_outcomes(c, symbol, tf)
        out.append({"symbol":symbol,"category":cat,"available":True,"bid":float(tick.bid),"ask":float(tick.ask),
          "spread":float(tick.ask-tick.bid),"quote_time":int(tick.time),"quote_age_seconds":quote_age,
          "quote_fresh":quote_age <= 180,"timeframe":tf,"signal":a['signal'],
          "score":a['score'],"score_label":f"{a['score']}/{a['max_score']} confluence (not win probability)","reason":a['reason'],
          "higher_timeframe": {"M5":"M15","M15":"H1","H1":"H4","H4":"D1"}[tf],
          "rsi":a.get("rsi"),"adx":a.get("adx"),
          "entry":entry if a['signal']!='WAIT' else None,"stop_loss":sl,"take_profit":tp,
          "last_candle":{"time":int(last['time']),"open":float(last['open']),"high":float(last['high']),"low":float(last['low']),"close":float(last['close'])}})
    c.commit(); c.close()
    return {"connected":True,"timeframe":tf,"scanned":len(selected),"markets":out}


@app.get("/api/history/candles")
def candle_history(symbol: str, tf: str = "M15", limit: int = Query(300, ge=1, le=5000)):
    c=db(); rows=c.execute("SELECT time,open,high,low,close,tick_volume FROM candles WHERE symbol=? AND tf=? ORDER BY time DESC LIMIT ?",(symbol,tf,limit)).fetchall(); c.close()
    return {"symbol":symbol,"timeframe":tf,"count":len(rows),"candles":[{"time":r[0],"open":r[1],"high":r[2],"low":r[3],"close":r[4],"volume":r[5]} for r in reversed(rows)]}


@app.get("/api/history/signals")
def signal_history(symbol: str = "", tf: str = "", limit: int = Query(200, ge=1, le=2000)):
    c=db(); sql="SELECT symbol,tf,candle_time,generated_at,side,entry,stop_loss,take_profit,score,reason,outcome FROM signals WHERE 1=1"; args=[]
    if symbol: sql += " AND symbol=?"; args.append(symbol)
    if tf: sql += " AND tf=?"; args.append(tf)
    sql += " ORDER BY generated_at DESC LIMIT ?"; args.append(limit)
    rows=c.execute(sql,args).fetchall(); c.close()
    return {"count":len(rows),"signals":[{"symbol":r[0],"timeframe":r[1],"candle_time":r[2],"generated_at":r[3],"side":r[4],"entry":r[5],"stop_loss":r[6],"take_profit":r[7],"score":r[8],"reason":r[9],"outcome":r[10]} for r in rows]}


@app.get("/api/history/summary")
def history_summary():
    c=db(); candles=c.execute("SELECT COUNT(*) FROM candles").fetchone()[0]; signals=c.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    latest=c.execute("SELECT MAX(time) FROM candles").fetchone()[0]; c.close()
    return {"candles_saved":candles,"signals_saved":signals,"latest_candle_time":latest,"database":os.path.basename(DB)}
