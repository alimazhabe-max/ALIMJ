"""Technical-analysis helpers extracted from finance.py.

This module keeps market calculation code focused and reduces the size of the
market facade. It lazily references runtime HTTP/logging dependencies from
finance.py after that module is initialized.
"""
from __future__ import annotations
import asyncio
from bot.features.market import finance as _f
from bot.logger import logger
from bot.utils.http_client import pooled_async_client, request_with_retry

# Compatibility aliases preserved from the original finance.py implementation.
# finance_ta is loaded through the finance facade after it is initialized.
_fetch_klines_interval = _f._fetch_klines_interval

async def _fetch_klines_for_ta(pair: str, limit: int = 200) -> list:
    """OHLCV از Binance Vision برای تحلیل تکنیکال"""
    try:
        async with pooled_async_client() as c:
            r = await request_with_retry("GET", 
                "https://data-api.binance.vision/api/v3/klines",
                params={"symbol": pair, "interval": "1h", "limit": limit},
            )
            if r.status_code == 200:
                return r.json() or []
            # OKX fallback
            okx = pair.replace("USDT", "-USDT")
            r2 = await request_with_retry("GET", 
                "https://www.okx.com/api/v5/market/candles",
                params={"instId": okx, "bar": "1H", "limit": str(min(limit, 300))},
            )
            if r2.status_code == 200:
                data = (r2.json() or {}).get("data") or []
                # OKX newest first → reverse; map to binance-like
                out = []
                for row in reversed(data):
                    out.append([int(row[0]), row[1], row[2], row[3], row[4], row[5]])
                return out
    except Exception as e:
        logger.warning(f"klines ta: {e}")
    return []


def _sma(arr: list, n: int):
    if len(arr) < n:
        return None
    return sum(arr[-n:]) / n


def _rsi(closes: list, period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(-period, 0):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _adx_approx(highs: list, lows: list, closes: list, period: int = 14) -> float | None:
    """تقریب ساده ADX"""
    if len(closes) < period * 2:
        return None
    trs = []
    dms_p, dms_m = [], []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
        up = highs[i] - highs[i - 1]
        dn = lows[i - 1] - lows[i]
        dms_p.append(up if up > dn and up > 0 else 0)
        dms_m.append(dn if dn > up and dn > 0 else 0)
    if len(trs) < period:
        return None
    atr = sum(trs[-period:]) / period
    if atr == 0:
        return 0.0
    di_p = 100 * (sum(dms_p[-period:]) / period) / atr
    di_m = 100 * (sum(dms_m[-period:]) / period) / atr
    denom = di_p + di_m
    if denom == 0:
        return 0.0
    dx = 100 * abs(di_p - di_m) / denom
    return dx


def _compute_ta(closes, highs, lows, vols) -> dict:
    out = {}
    out["sma20"] = _sma(closes, 20)
    out["sma50"] = _sma(closes, 50) if len(closes) >= 50 else _sma(closes, 30)
    out["rsi"] = _rsi(closes, 14)
    out["adx"] = _adx_approx(highs, lows, closes, 14)
    if vols and len(vols) >= 20:
        avg_vol = sum(vols[-20:]) / 20
        out["vol_ratio"] = (vols[-1] / avg_vol) if avg_vol else 1.0
    # روند
    sma20, sma50 = out.get("sma20"), out.get("sma50")
    price = closes[-1]
    if sma20 and sma50:
        if price > sma20 > sma50:
            out["trend"] = "صعودی"
        elif price < sma20 < sma50:
            out["trend"] = "نزولی"
        else:
            out["trend"] = "خنثی"
    elif sma20:
        out["trend"] = "صعودی" if price > sma20 else "نزولی"
    else:
        out["trend"] = "خنثی"
    # شیب اخیر
    if len(closes) >= 24:
        chg = (closes[-1] - closes[-24]) / closes[-24] * 100
        out["chg_24h_bar"] = chg
        if out["trend"] == "خنثی":
            if chg > 2:
                out["trend"] = "صعودی"
            elif chg < -2:
                out["trend"] = "نزولی"
    return out



def _atr(highs, lows, closes, period: int = 14) -> float | None:
    """Average True Range"""
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def _detect_candle_patterns(opens, highs, lows, closes) -> list:
    """تشخیص ساده Engulfing و Pin Bar روی آخرین کندل‌ها"""
    patterns = []
    n = len(closes)
    if n < 3 or len(opens) < n:
        return patterns
    o, h, l, c = opens[-1], highs[-1], lows[-1], closes[-1]
    po, ph, pl, pc = opens[-2], highs[-2], lows[-2], closes[-2]
    body = abs(c - o)
    range_ = max(h - l, 1e-12)
    upper = h - max(c, o)
    lower = min(c, o) - l
    prev_body = abs(pc - po)

    # Bullish Engulfing
    if pc < po and c > o and c >= po and o <= pc and body > prev_body * 0.9:
        patterns.append("پوششی صعودی (Bullish Engulfing) 🟢")
    # Bearish Engulfing
    if pc > po and c < o and c <= po and o >= pc and body > prev_body * 0.9:
        patterns.append("پوششی نزولی (Bearish Engulfing) 🔴")

    # Pin Bar / Hammer (سایه پایین بلند)
    if lower >= body * 2 and upper <= body * 0.5 and body / range_ < 0.35:
        if c >= o:
            patterns.append("پین‌بار صعودی / چکش 🟢")
        else:
            patterns.append("پین‌بار با بدنه منفی (احتیاط) 🟡")
    # Shooting Star (سایه بالا بلند)
    if upper >= body * 2 and lower <= body * 0.5 and body / range_ < 0.35:
        if c <= o:
            patterns.append("ستاره دنباله‌دار (Shooting Star) 🔴")
        else:
            patterns.append("پین‌بار معکوس (احتیاط) 🟡")

    return patterns


def _score_timeframe(ta: dict) -> tuple:
    """امتیاز 1-10 و جهت برای یک تایم‌فریم"""
    score = 5
    trend = ta.get("trend") or "خنثی"
    rsi = ta.get("rsi")
    adx = ta.get("adx") or 0
    direction = "خنثی"

    if trend == "صعودی":
        score += 2
        direction = "صعودی"
    elif trend == "نزولی":
        score += 2
        direction = "نزولی"

    if rsi is not None:
        if direction == "صعودی" and 40 <= rsi <= 68:
            score += 1
        elif direction == "نزولی" and 32 <= rsi <= 60:
            score += 1
        elif direction == "صعودی" and rsi >= 75:
            score -= 2
        elif direction == "نزولی" and rsi <= 25:
            score -= 2

    if adx >= 25:
        score += 1
    elif adx < 18:
        score -= 2
        direction = "رنج/ضعیف"

    # الگوها
    for p in ta.get("patterns") or []:
        if "صعودی" in p or "چکش" in p:
            if direction != "نزولی":
                score += 1
        if "نزولی" in p or "دنباله‌دار" in p:
            if direction != "صعودی":
                score += 1

    score = max(1, min(10, score))
    return score, direction, adx


async def _mtf_bundle(pair: str) -> dict:
    """تحلیل موازی 1H / 4H / 1D + تضاد"""
    k1, k4, kd = await asyncio.gather(
        _fetch_klines_interval(pair, "1h", 120),
        _fetch_klines_interval(pair, "4h", 120),
        _fetch_klines_interval(pair, "1d", 120),
    )

    def pack(klines):
        opens, highs, lows, closes, vols = [], [], [], [], []
        for k in klines or []:
            try:
                opens.append(float(k[1])); highs.append(float(k[2]))
                lows.append(float(k[3])); closes.append(float(k[4]))
                vols.append(float(k[5]))
            except Exception:
                continue
        if len(closes) < 30:
            return {}, opens, highs, lows, closes
        ta = _compute_ta(closes, highs, lows, vols)
        ta["atr"] = _atr(highs, lows, closes, 14)
        ta["patterns"] = _detect_candle_patterns(opens, highs, lows, closes)
        score, direction, adx = _score_timeframe(ta)
        ta["tf_score"] = score
        ta["tf_dir"] = direction
        return ta, opens, highs, lows, closes

    t1, *_ = pack(k1)
    t4, *_ = pack(k4)
    td, o_d, h_d, l_d, c_d = pack(kd)

    dirs = {
        "1H": (t1 or {}).get("tf_dir", "—"),
        "4H": (t4 or {}).get("tf_dir", "—"),
        "1D": (td or {}).get("tf_dir", "—"),
    }
    scores = {
        "1H": (t1 or {}).get("tf_score"),
        "4H": (t4 or {}).get("tf_score"),
        "1D": (td or {}).get("tf_score"),
    }

    # تضاد
    conflict = False
    bull = sum(1 for d in dirs.values() if d == "صعودی")
    bear = sum(1 for d in dirs.values() if d == "نزولی")
    if bull >= 1 and bear >= 1:
        conflict = True

    daily_adx = (td or {}).get("adx") or 0
    force_wait = daily_adx < 18 if td else False

    return {
        "1h": t1 or {},
        "4h": t4 or {},
        "1d": td or {},
        "dirs": dirs,
        "scores": scores,
        "conflict": conflict,
        "force_wait": force_wait,
        "daily_adx": daily_adx,
        "daily_klines": (o_d, h_d, l_d, c_d),
    }



def _market_structure(highs, lows, closes) -> dict:
    """ساختار ساده: HH/HL یا LH/LL + BOS تقریبی"""
    if len(closes) < 20:
        return {"structure": "نامشخص", "bos": None}
    # swing تقریبی روی 5 کندل
    def swings(arr, mode="high"):
        pts = []
        for i in range(2, len(arr) - 2):
            if mode == "high" and arr[i] == max(arr[i-2:i+3]):
                pts.append((i, arr[i]))
            if mode == "low" and arr[i] == min(arr[i-2:i+3]):
                pts.append((i, arr[i]))
        return pts[-4:]
    sh = swings(highs, "high")
    sl = swings(lows, "low")
    structure = "رنج"
    bos = None
    if len(sh) >= 2 and len(sl) >= 2:
        if sh[-1][1] > sh[-2][1] and sl[-1][1] > sl[-2][1]:
            structure = "صعودی (HH/HL)"
            if closes[-1] > sh[-1][1]:
                bos = "BOS صعودی — شکست سقف اخیر"
        elif sh[-1][1] < sh[-2][1] and sl[-1][1] < sl[-2][1]:
            structure = "نزولی (LH/LL)"
            if closes[-1] < sl[-1][1]:
                bos = "BOS نزولی — شکست کف اخیر"
        elif sh[-1][1] < sh[-2][1] and sl[-1][1] > sl[-2][1]:
            structure = "احتمال CHOCH / فشردگی"
            bos = "تغییر ساختار محتمل"
    return {"structure": structure, "bos": bos, "last_swing_high": sh[-1][1] if sh else None, "last_swing_low": sl[-1][1] if sl else None}


def _rsi_divergence(closes, period: int = 14) -> str | None:
    """واگرایی ساده RSI روی ۲۰ کندل آخر"""
    if len(closes) < period + 25:
        return None
    # RSI series rough
    rsis = []
    for end in range(period + 1, len(closes) + 1):
        r = _rsi(closes[:end], period)
        if r is not None:
            rsis.append(r)
    if len(rsis) < 20:
        return None
    c = closes[-20:]
    r = rsis[-20:]
    # سقف قیمت vs RSI
    i_px_hi = max(range(len(c)), key=lambda i: c[i])
    i_rsi_hi = max(range(len(r)), key=lambda i: r[i])
    i_px_lo = min(range(len(c)), key=lambda i: c[i])
    i_rsi_lo = min(range(len(r)), key=lambda i: r[i])
    # bearish div: price higher high near end, rsi lower high
    if i_px_hi >= 12 and c[i_px_hi] >= max(c[:10]) and r[i_px_hi] < max(r[:10]) - 3:
        return "واگرایی نزولی RSI — ضعف در سقف"
    if i_px_lo >= 12 and c[i_px_lo] <= min(c[:10]) and r[i_px_lo] > min(r[:10]) + 3:
        return "واگرایی صعودی RSI — ضعف فروش در کف"
    return None


def _volume_breakout(closes, vols, resistance, support) -> str | None:
    if not closes or not vols or len(vols) < 20:
        return None
    avg = sum(vols[-20:]) / 20
    last_v = vols[-1]
    last_c = closes[-1]
    ratio = last_v / avg if avg else 1
    if resistance and last_c > resistance * 0.998 and ratio >= 1.4:
        return f"شکست مقاومت با حجم قوی (×{ratio:.1f})"
    if support and last_c < support * 1.002 and ratio >= 1.4:
        return f"شکست حمایت با حجم قوی (×{ratio:.1f})"
    if ratio >= 1.8:
        return f"حجم غیرعادی ×{ratio:.1f} میانگین"
    if ratio < 0.6:
        return "حجم ضعیف — شکست‌ها کم‌اعتبارتر"
    return None


def _demand_supply_zone(highs, lows, closes) -> tuple:
    """بازه تقریبی تقاضا/عرضه از ۱۰–۳۰ کندل قبل"""
    if len(closes) < 30:
        return None, None
    seg_l = lows[-30:-5]
    seg_h = highs[-30:-5]
    if not seg_l or not seg_h:
        return None, None
    demand = (min(seg_l), sorted(seg_l)[max(0, len(seg_l)//4)])
    supply = (sorted(seg_h)[max(0, 3*len(seg_h)//4 - 1)], max(seg_h))
    return demand, supply


def _mtf_convergence(mtf: dict) -> tuple:
    """(متن همگرایی، قدرت 1-10)"""
    dirs = mtf.get("dirs") or {}
    scores = mtf.get("scores") or {}
    vals = [dirs.get(k) for k in ("1H", "4H", "1D")]
    bull = sum(1 for d in vals if d == "صعودی")
    bear = sum(1 for d in vals if d == "نزولی")
    avg_sc = [scores.get(k) for k in ("1H", "4H", "1D") if scores.get(k)]
    avg = sum(avg_sc) / len(avg_sc) if avg_sc else 5
    if bull == 3:
        return "همگرایی کامل صعودی ۳/۳", min(10, int(avg + 2))
    if bear == 3:
        return "همگرایی کامل نزولی ۳/۳", min(10, int(avg + 2))
    if bull == 2 and bear == 0:
        return "همگرایی جزئی صعودی ۲/۳", int(avg)
    if bear == 2 and bull == 0:
        return "همگرایی جزئی نزولی ۲/۳", int(avg)
    if bull and bear:
        return "عدم همگرایی — تضاد تایم‌فریم‌ها", max(1, int(avg - 2))
    return "همگرایی ضعیف / رنج", max(1, int(avg - 1))


