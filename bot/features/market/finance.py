"""
مالی و بازار — ارز، فلزات، سکه + کریپتو کامل
نمودار قیمت + مبدل همه ارزهای دیجیتال + تحلیل چندمنبعی (CoinGecko + Binance + CoinPaprika + Fear&Greed + تلاش Coinglass)
"""
import re
import io
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any
import httpx
from bs4 import BeautifulSoup
from bot.config import config
from bot.logger import logger
from bot.utils.http_resilience import pooled_client
from bot.utils.http_client import pooled_async_client, request_with_retry

_cache = {}
_cache_t = {}
_cache_locks = {}

async def _cache_lock(key):
    lock = _cache_locks.get(key)
    if lock is None:
        lock = _cache_locks[key] = asyncio.Lock()
    return lock

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}


# Core pricing/conversion operations live in finance_core.py.
from bot.features.market.finance_core import (
    TGJU_SLUGS, SYMBOL_TO_ID, pn, _parse_price, _fetch_tgju_bulk, _tgju_price,
    _get_usd_rial, resolve_coin_id, _crypto_simple, _top_from_coinlore,
    _top_from_paprika, get_top_crypto, convert_crypto, full_market_prices,
    rial_toman, convert_currency, profit_loss, parse_profit, parse_currency_input,
)

# ─────────────────────────────────────────────────────────────────────────────
# نمودار قیمت کریپتو (باگ‌فیکس‌شده)
# ─────────────────────────────────────────────────────────────────────────────

async def get_crypto_chart(symbol: str, days: int = 7) -> Tuple[Optional[bytes], str]:
    """
    نمودار چندپنلی شبیه TradingView/AlgoAnalyzer:
    کندل + Bollinger + EMA + حجم + ADX + RSI
    """
    try:
        days = max(1, min(int(days or 7), 365))
    except Exception:
        days = 7

    symbol_clean = (symbol or "").lower().strip().replace(" ", "").replace("‌", "")
    for junk in ("نمودار", "chart", "قیمت", "روز", "روزه", "price", "تحلیل"):
        symbol_clean = symbol_clean.replace(junk, "")
    symbol_clean = symbol_clean.replace("usdt", "").strip() or "btc"

    coin_id = await resolve_coin_id(symbol_clean)
    _sym_map = {
        "bitcoin": "BTC", "ethereum": "ETH", "tether": "USDT", "binancecoin": "BNB",
        "solana": "SOL", "ripple": "XRP", "the-open-network": "TON", "dogecoin": "DOGE",
        "cardano": "ADA", "tron": "TRX", "chainlink": "LINK", "litecoin": "LTC",
        "polkadot": "DOT", "avalanche-2": "AVAX", "shiba-inu": "SHIB",
        "matic-network": "MATIC", "near": "NEAR", "pepe": "PEPE", "sui": "SUI",
    }
    pair = symbol_clean.upper().replace("USDT", "").replace("-", "") + "USDT"
    if coin_id and coin_id in _sym_map:
        pair = _sym_map[coin_id] + "USDT"
    elif symbol_clean in _sym_map:
        pair = _sym_map[symbol_clean] + "USDT"

    # انتخاب interval بر اساس days
    if days <= 3:
        interval, limit = "15m", min(300, days * 96)
    elif days <= 14:
        interval, limit = "1h", min(400, days * 24)
    elif days <= 60:
        interval, limit = "4h", min(400, days * 6)
    else:
        interval, limit = "1d", min(400, days)

    klines = await _fetch_klines_interval(pair, interval, int(limit))
    if not klines or len(klines) < 20:
        return None, (
            f"❌ داده نموداری برای {pair} در دسترس نیست.\n"
            "مثال: btc ، eth ، sol ، ton"
        )

    try:
        import numpy as np
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Rectangle, FancyBboxPatch
        from matplotlib.collections import LineCollection
        plt.rcParams.update({
            "axes.unicode_minus": False,
            "font.family": "DejaVu Sans",
            "figure.facecolor": "#0b0e11",
            "axes.facecolor": "#0b0e11",
            "savefig.facecolor": "#0b0e11",
            "text.color": "#e5e7eb",
            "axes.labelcolor": "#9ca3af",
            "xtick.color": "#9ca3af",
            "ytick.color": "#9ca3af",
            "axes.edgecolor": "#1f2937",
            "grid.color": "#1f2937",
            "grid.linestyle": "-",
            "grid.linewidth": 0.6,
            "grid.alpha": 0.9,
        })
    except ImportError as e:
        return None, f"❌ کتابخانه رسم نصب نیست: {e}"

    opens = np.array([float(k[1]) for k in klines], dtype=float)
    highs = np.array([float(k[2]) for k in klines], dtype=float)
    lows = np.array([float(k[3]) for k in klines], dtype=float)
    closes = np.array([float(k[4]) for k in klines], dtype=float)
    vols = np.array([float(k[5]) for k in klines], dtype=float)
    n = len(closes)
    x = np.arange(n, dtype=float)

    def _ema(arr, period):
        out = np.zeros(len(arr), dtype=float)
        out[0] = arr[0]
        a = 2.0 / (period + 1)
        for i in range(1, len(arr)):
            out[i] = a * arr[i] + (1 - a) * out[i - 1]
        return out

    def _rsi_arr(c, period=14):
        out = np.full(len(c), np.nan)
        if len(c) <= period:
            return out
        diff = np.diff(c)
        gains = np.where(diff > 0, diff, 0.0)
        losses = np.where(diff < 0, -diff, 0.0)
        ag = gains[:period].mean()
        al = losses[:period].mean()
        out[period] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
        for i in range(period, len(diff)):
            ag = (ag * (period - 1) + gains[i]) / period
            al = (al * (period - 1) + losses[i]) / period
            out[i + 1] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
        return out

    def _adx_arr(h, l, c, period=14):
        out = np.full(len(c), np.nan)
        if len(c) < period + 2:
            return out
        tr = np.zeros(len(c))
        dp = np.zeros(len(c))
        dm = np.zeros(len(c))
        for i in range(1, len(c)):
            tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
            up = h[i] - h[i - 1]
            dn = l[i - 1] - l[i]
            dp[i] = up if up > dn and up > 0 else 0
            dm[i] = dn if dn > up and dn > 0 else 0
        atr = np.zeros(len(c))
        atr[period] = tr[1:period + 1].mean()
        for i in range(period + 1, len(c)):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
        dxs = []
        for i in range(period, len(c)):
            atr_v = atr[i] if atr[i] > 0 else 1e-9
            di_p = 100 * (dp[i - period + 1:i + 1].mean()) / atr_v
            di_m = 100 * (dm[i - period + 1:i + 1].mean()) / atr_v
            s = di_p + di_m
            dx = 0 if s == 0 else 100 * abs(di_p - di_m) / s
            dxs.append(dx)
            out[i] = float(np.mean(dxs[-period:])) if len(dxs) >= period else dx
        return out

    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50) if n >= 50 else _ema(closes, max(10, n // 3))
    ema100 = _ema(closes, 100) if n >= 100 else None
    bb_period = 20
    sma = np.array([closes[max(0, i - bb_period + 1):i + 1].mean() for i in range(n)])
    std = np.array([closes[max(0, i - bb_period + 1):i + 1].std() for i in range(n)])
    bb_u, bb_l = sma + 2 * std, sma - 2 * std
    rsi = _rsi_arr(closes, 14)
    adx = _adx_arr(highs, lows, closes, 14)

    # رنگ‌های حرفه‌ای
    C_UP = "#26a69a"
    C_DN = "#ef5350"
    C_EMA20 = "#42a5f5"
    C_EMA50 = "#ffa726"
    C_EMA100 = "#ab47bc"
    C_BB = "#5c6bc0"
    C_GRID = "#1e222d"
    C_TEXT = "#d1d4dc"
    C_MUTED = "#787b86"

    try:
        fig = plt.figure(figsize=(12, 9), dpi=140)
        gs = fig.add_gridspec(4, 1, height_ratios=[3.4, 0.85, 0.85, 0.85], hspace=0.06)
        ax_p = fig.add_subplot(gs[0])
        ax_v = fig.add_subplot(gs[1], sharex=ax_p)
        ax_a = fig.add_subplot(gs[2], sharex=ax_p)
        ax_r = fig.add_subplot(gs[3], sharex=ax_p)

        for ax in (ax_p, ax_v, ax_a, ax_r):
            ax.set_facecolor("#131722")
            ax.tick_params(colors=C_MUTED, labelsize=8)
            ax.grid(True, color=C_GRID, linewidth=0.7)
            for spine in ax.spines.values():
                spine.set_color("#2a2e39")

        # Bollinger fill
        ax_p.fill_between(x, bb_l, bb_u, color=C_BB, alpha=0.12, zorder=1)
        ax_p.plot(x, bb_u, color=C_BB, linewidth=0.7, alpha=0.5, linestyle="--", zorder=2)
        ax_p.plot(x, bb_l, color=C_BB, linewidth=0.7, alpha=0.5, linestyle="--", zorder=2)
        ax_p.plot(x, sma, color=C_BB, linewidth=0.9, alpha=0.7, zorder=2)

        # Candles — wick + body تمیز
        width = 0.62
        for i in range(n):
            up = closes[i] >= opens[i]
            color = C_UP if up else C_DN
            ax_p.plot([i, i], [lows[i], highs[i]], color=color, linewidth=1.0, solid_capstyle="round", zorder=3)
            body = abs(closes[i] - opens[i])
            bottom = min(opens[i], closes[i])
            if body < (highs[i] - lows[i]) * 0.002:
                body = max((highs[i] - lows[i]) * 0.015, closes[i] * 0.00008)
            ax_p.add_patch(Rectangle(
                (i - width / 2, bottom), width, body,
                facecolor=color, edgecolor=color, linewidth=0.4, zorder=4, alpha=0.95,
            ))

        ax_p.plot(x, ema20, color=C_EMA20, linewidth=1.35, label="EMA 20", zorder=5)
        ax_p.plot(x, ema50, color=C_EMA50, linewidth=1.35, label="EMA 50", zorder=5)
        if ema100 is not None:
            ax_p.plot(x, ema100, color=C_EMA100, linewidth=1.2, label="EMA 100", zorder=5)

        last = float(closes[-1])
        chg = ((closes[-1] - closes[0]) / closes[0] * 100) if closes[0] else 0
        chg_c = C_UP if chg >= 0 else C_DN
        ax_p.set_title(
            f"{pair}   •   {days}D ({interval})   •   ${last:,.2f}   ({chg:+.2f}%)",
            fontsize=13, fontweight="bold", color=C_TEXT, loc="left", pad=10,
        )
        leg = ax_p.legend(loc="upper left", fontsize=8, frameon=True, fancybox=True)
        leg.get_frame().set_facecolor("#1c2030")
        leg.get_frame().set_edgecolor("#2a2e39")
        for txt in leg.get_texts():
            txt.set_color(C_TEXT)
        ax_p.set_ylabel("Price (USDT)", fontsize=9, color=C_MUTED)
        # آخرین قیمت خط افقی
        ax_p.axhline(last, color=chg_c, linewidth=0.8, linestyle=":", alpha=0.7, zorder=2)
        ax_p.margins(x=0.01)
        plt.setp(ax_p.get_xticklabels(), visible=False)

        # Volume
        vcolors = [C_UP if closes[i] >= opens[i] else C_DN for i in range(n)]
        ax_v.bar(x, vols, color=vcolors, width=0.7, alpha=0.85, zorder=3)
        ax_v.set_ylabel("Volume", fontsize=8, color=C_MUTED)
        plt.setp(ax_v.get_xticklabels(), visible=False)
        ax_v.margins(x=0.01)

        # ADX
        ax_a.plot(x, adx, color="#b2b5be", linewidth=1.25, label="ADX(14)", zorder=3)
        ax_a.axhline(25, color="#787b86", linestyle="--", linewidth=0.8, alpha=0.8)
        ax_a.fill_between(x, adx, 25, where=(~np.isnan(adx)) & (adx >= 25), color="#26a69a", alpha=0.15)
        ax_a.set_ylabel("ADX", fontsize=8, color=C_MUTED)
        ax_a.set_ylim(0, max(60, np.nanmax(adx) * 1.15 if np.nanmax(adx) == np.nanmax(adx) else 60))
        la = ax_a.legend(loc="upper left", fontsize=7, frameon=True)
        la.get_frame().set_facecolor("#1c2030")
        la.get_frame().set_edgecolor("#2a2e39")
        for txt in la.get_texts():
            txt.set_color(C_TEXT)
        plt.setp(ax_a.get_xticklabels(), visible=False)
        ax_a.margins(x=0.01)

        # RSI
        ax_r.plot(x, rsi, color="#e0e3eb", linewidth=1.25, label="RSI(14)", zorder=3)
        ax_r.axhline(70, color=C_DN, linestyle="--", linewidth=0.8, alpha=0.7)
        ax_r.axhline(30, color=C_UP, linestyle="--", linewidth=0.8, alpha=0.7)
        ax_r.axhline(50, color="#787b86", linestyle=":", linewidth=0.6, alpha=0.5)
        ax_r.fill_between(x, 70, 100, color=C_DN, alpha=0.06)
        ax_r.fill_between(x, 0, 30, color=C_UP, alpha=0.06)
        ax_r.set_ylim(0, 100)
        ax_r.set_ylabel("RSI", fontsize=8, color=C_MUTED)
        lr = ax_r.legend(loc="upper left", fontsize=7, frameon=True)
        lr.get_frame().set_facecolor("#1c2030")
        lr.get_frame().set_edgecolor("#2a2e39")
        for txt in lr.get_texts():
            txt.set_color(C_TEXT)
        ax_r.margins(x=0.01)

        # X labels
        step = max(1, n // 7)
        ticks = list(range(0, n, step))
        if n - 1 not in ticks:
            ticks.append(n - 1)
        labels = []
        for i in ticks:
            ts = int(klines[i][0])
            if ts < 1e12:
                ts *= 1000
            dt = datetime.utcfromtimestamp(ts / 1000.0)
            labels.append(dt.strftime("%m/%d" if days > 5 else "%m/%d %H:%M"))
        ax_r.set_xticks(ticks)
        ax_r.set_xticklabels(labels, rotation=0, fontsize=8, color=C_MUTED)

        fig.subplots_adjust(left=0.07, right=0.98, top=0.93, bottom=0.06)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=140, facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close(fig)
        buf.seek(0)
        png = buf.read()
    except Exception as e:
        logger.error(f"chart draw: {e}")
        try:
            plt.close("all")
        except Exception:
            pass
        return None, f"❌ خطا در رسم نمودار: {e}"

    first, last = float(closes[0]), float(closes[-1])
    chg = ((last - first) / first * 100) if first else 0
    emoji = "🟢" if chg >= 0 else "🔴"
    caption = (
        f"📊 {pair} | {days}D ({interval})\n"
        f"${first:,.2f} → ${last:,.2f}  {emoji} {chg:+.2f}%\n"
        f"H/L: ${float(highs.max()):,.2f} / ${float(lows.min()):,.2f}"
    )
    return png, caption



async def _fetch_klines_interval(pair: str, interval: str, limit: int) -> list:
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        async with pooled_async_client() as c:
            r = await request_with_retry("GET", 
                "https://data-api.binance.vision/api/v3/klines",
                params={"symbol": pair, "interval": interval, "limit": limit},
            )
            if r.status_code == 200:
                data = r.json() or []
                if data:
                    return data
            # OKX map
            okx_bar = {"15m": "15m", "1h": "1H", "4h": "4H", "1d": "1D"}.get(interval, "1H")
            okx_sym = pair.replace("USDT", "-USDT")
            r2 = await request_with_retry("GET", 
                "https://www.okx.com/api/v5/market/candles",
                params={"instId": okx_sym, "bar": okx_bar, "limit": str(min(limit, 300))},
            )
            if r2.status_code == 200:
                rows = (r2.json() or {}).get("data") or []
                out = []
                for row in reversed(rows):
                    out.append([int(row[0]), row[1], row[2], row[3], row[4], row[5]])
                return out
    except Exception as e:
        logger.warning(f"klines interval: {e}")
    return []



async def _fetch_coingecko_detail(coin_id: str) -> dict:
    try:
        async with pooled_async_client() as c:
            r = await request_with_retry("GET", 
                f"https://api.coingecko.com/api/v3/coins/{coin_id}",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "true",
                    "community_data": "false",
                    "developer_data": "false",
                },
            )
            if r.status_code == 200:
                return r.json() or {}
    except Exception as e:
        logger.warning(f"cg detail: {e}")
    return {}


async def _fetch_binance_futures(symbol: str) -> dict:
    """Funding, OI, حجم + نسبت لانگ/شورت حساب‌ها و تریدرهای برتر"""
    sym = (symbol or "").upper().replace("USDT", "").replace("-", "") + "USDT"
    out = {}
    try:
        async with pooled_async_client() as c:
            r = await request_with_retry("GET", "https://fapi.binance.com/fapi/v1/premiumIndex", params={"symbol": sym})
            if r.status_code == 200:
                d = r.json()
                out["funding_rate"] = float(d.get("lastFundingRate") or 0) * 100
                out["mark_price"] = float(d.get("markPrice") or 0)
            r2 = await request_with_retry("GET", "https://fapi.binance.com/fapi/v1/openInterest", params={"symbol": sym})
            if r2.status_code == 200:
                out["open_interest"] = float(r2.json().get("openInterest") or 0)
            r3 = await request_with_retry("GET", "https://fapi.binance.com/fapi/v1/ticker/24hr", params={"symbol": sym})
            if r3.status_code == 200:
                tk = r3.json()
                out["volume_24h"] = float(tk.get("quoteVolume") or 0)
                out["price_change_pct"] = float(tk.get("priceChangePercent") or 0)

            # نسبت لانگ/شورت — حساب‌های معمولی (global)
            r4 = await request_with_retry("GET", 
                "https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
                params={"symbol": sym, "period": "1h", "limit": 1},
            )
            if r4.status_code == 200:
                arr = r4.json() or []
                if arr:
                    row = arr[-1]
                    out["ls_global_ratio"] = float(row.get("longShortRatio") or 0)
                    out["ls_global_long"] = float(row.get("longAccount") or 0) * 100
                    out["ls_global_short"] = float(row.get("shortAccount") or 0) * 100

            # نسبت لانگ/شورت — تریدرهای برتر
            r5 = await request_with_retry("GET", 
                "https://fapi.binance.com/futures/data/topLongShortAccountRatio",
                params={"symbol": sym, "period": "1h", "limit": 1},
            )
            if r5.status_code == 200:
                arr = r5.json() or []
                if arr:
                    row = arr[-1]
                    out["ls_top_ratio"] = float(row.get("longShortRatio") or 0)
                    out["ls_top_long"] = float(row.get("longAccount") or 0) * 100
                    out["ls_top_short"] = float(row.get("shortAccount") or 0) * 100

            # نسبت پوزیشن (نه فقط تعداد حساب) تریدرهای برتر
            r6 = await request_with_retry("GET", 
                "https://fapi.binance.com/futures/data/topLongShortPositionRatio",
                params={"symbol": sym, "period": "1h", "limit": 1},
            )
            if r6.status_code == 200:
                arr = r6.json() or []
                if arr:
                    row = arr[-1]
                    out["ls_pos_ratio"] = float(row.get("longShortRatio") or 0)
                    out["ls_pos_long"] = float(row.get("longAccount") or 0) * 100
                    out["ls_pos_short"] = float(row.get("shortAccount") or 0) * 100
    except Exception as e:
        logger.warning(f"binance futures {sym}: {e}")

    # Fallback OKX long/short اگر Binance خالی/مسدود بود
    if out.get("ls_global_ratio") is None:
        try:
            base = sym.replace("USDT", "")
            async with pooled_async_client() as c:
                r = await request_with_retry("GET", 
                    "https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio",
                    params={"ccy": base},
                )
                if r.status_code == 200:
                    arr = (r.json() or {}).get("data") or []
                    if arr:
                        # [ts, ratio] — ratio = long/short
                        ratio = float(arr[0][1])
                        # long% = ratio/(1+ratio)*100
                        long_pct = ratio / (1 + ratio) * 100
                        short_pct = 100 - long_pct
                        out["ls_global_ratio"] = ratio
                        out["ls_global_long"] = long_pct
                        out["ls_global_short"] = short_pct
                        out["ls_source"] = "okx"
                r2 = await request_with_retry("GET", 
                    "https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio-contract-top-trader",
                    params={"instId": f"{base}-USDT-SWAP"},
                )
                if r2.status_code == 200:
                    arr = (r2.json() or {}).get("data") or []
                    if arr:
                        ratio = float(arr[0][1])
                        long_pct = ratio / (1 + ratio) * 100
                        short_pct = 100 - long_pct
                        out["ls_top_ratio"] = ratio
                        out["ls_top_long"] = long_pct
                        out["ls_top_short"] = short_pct
        except Exception as e:
            logger.warning(f"okx ls {sym}: {e}")
    return out


def _format_long_short(binance: dict) -> list:
    """خطوط فارسی نسبت لانگ/شورت"""
    if not binance:
        return []
    lines = []
    gl = binance.get("ls_global_long")
    gs = binance.get("ls_global_short")
    gr = binance.get("ls_global_ratio")
    if gl is not None and gs is not None:
        bias = "لانگ غالب 🟢" if gl > gs + 5 else ("شورت غالب 🔴" if gs > gl + 5 else "متعادل ⚪")
        lines.append(f"👥 حساب‌ها (عمومی): لانگ {gl:.1f}% | شورت {gs:.1f}% — {bias}")
        if gr:
            lines.append(f"   نسبت L/S: {gr:.3f}")
    tl = binance.get("ls_top_long")
    ts = binance.get("ls_top_short")
    tr = binance.get("ls_top_ratio")
    if tl is not None and ts is not None:
        bias = "لانگ غالب 🟢" if tl > ts + 5 else ("شورت غالب 🔴" if ts > tl + 5 else "متعادل ⚪")
        lines.append(f"🏆 تریدرهای برتر (حساب): لانگ {tl:.1f}% | شورت {ts:.1f}% — {bias}")
        if tr:
            lines.append(f"   نسبت L/S: {tr:.3f}")
    pl = binance.get("ls_pos_long")
    ps = binance.get("ls_pos_short")
    pr = binance.get("ls_pos_ratio")
    if pl is not None and ps is not None:
        bias = "لانگ غالب 🟢" if pl > ps + 5 else ("شورت غالب 🔴" if ps > pl + 5 else "متعادل ⚪")
        lines.append(f"📦 حجم پوزیشن برتر: لانگ {pl:.1f}% | شورت {ps:.1f}% — {bias}")
        if pr:
            lines.append(f"   نسبت L/S: {pr:.3f}")
    # تفسیر کوتاه
    if gl is not None and tl is not None:
        if gl > 60 and tl < 45:
            lines.append("⚠️ عموم لانگ شلوغ‌اند ولی برترها محتاط‌تر — احتیاط در لانگ")
        elif gs > 60 and ts < 45:
            lines.append("⚠️ عموم شورت شلوغ‌اند ولی برترها محتاط‌تر — احتیاط در شورت")
    return lines


async def _fetch_fear_greed(limit: int = 7):
    """شاخص ترس و طمع — امروز + میانگین چند روز"""
    try:
        async with pooled_async_client() as c:
            r = await request_with_retry("GET", "https://api.alternative.me/fng/", params={"limit": str(limit)})
            if r.status_code == 200:
                data = (r.json() or {}).get("data") or []
                if not data:
                    return None
                today = data[0]
                vals = []
                for d in data:
                    try:
                        vals.append(int(d.get("value")))
                    except Exception:
                        pass
                out = {
                    "value": today.get("value"),
                    "value_classification": today.get("value_classification"),
                    "timestamp": today.get("timestamp"),
                    "history": data,
                    "avg_7": (sum(vals) / len(vals)) if vals else None,
                    "prev": int(data[1]["value"]) if len(data) > 1 else None,
                }
                return out
    except Exception as e:
        logger.warning(f"fear greed: {e}")
    return None


def _format_fear_greed(fg) -> list:
    """خطوط فارسی کامل برای F&G"""
    if not fg:
        return ["😨 ترس و طمع: در دسترس نیست"]
    try:
        val = int(fg.get("value") or 0)
    except Exception:
        val = 0
    cls = (fg.get("value_classification") or "").strip()
    # نقشه فارسی + ایموجی
    if val <= 24:
        fa, em = "ترس شدید", "😱"
    elif val <= 44:
        fa, em = "ترس", "😨"
    elif val <= 55:
        fa, em = "خنثی", "😐"
    elif val <= 74:
        fa, em = "طمع", "😊"
    else:
        fa, em = "طمع شدید", "🤑"
    lines = [f"😨 شاخص ترس و طمع: {val}/100 — {fa} {em}"]
    if cls:
        lines.append(f"   طبقه انگلیسی: {cls}")
    prev = fg.get("prev")
    avg7 = fg.get("avg_7")
    if prev is not None:
        delta = val - int(prev)
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
        lines.append(f"   تغییر روزانه: {arrow} {delta:+d}")
    if avg7 is not None:
        lines.append(f"   میانگین ۷روز: {avg7:.0f}")
    # تفسیر معاملاتی کوتاه
    if val <= 25:
        lines.append("   تفسیر: ترس افراطی — احتمال فرصت خرید میان‌مدت (نه سیگنال ورود فوری)")
    elif val >= 75:
        lines.append("   تفسیر: طمع افراطی — احتیاط در لانگ‌های جدید")
    return lines



async def analyze_crypto(*args, **kwargs):
    from bot.features.market.finance_crypto import analyze_crypto as _fn
    return await _fn(*args, **kwargs)

def _default_guide(*args, **kwargs):
    from bot.features.market.finance_crypto import _default_guide as _fn
    return _fn(*args, **kwargs)

def _build_smart_summary_pair(*args, **kwargs):
    from bot.features.market.finance_crypto import _build_smart_summary_pair as _fn
    return _fn(*args, **kwargs)

async def _fetch_fundamentals(*args, **kwargs):
    from bot.features.market.finance_crypto import _fetch_fundamentals as _fn
    return await _fn(*args, **kwargs)

def _build_smart_summary(*args, **kwargs):
    from bot.features.market.finance_crypto import _build_smart_summary as _fn
    return _fn(*args, **kwargs)




async def _fetch_klines_for_ta(*args, **kwargs):
    from bot.features.market.finance_ta import _fetch_klines_for_ta as _fn
    return await _fn(*args, **kwargs)

def _sma(*args, **kwargs):
    from bot.features.market.finance_ta import _sma as _fn
    return _fn(*args, **kwargs)

def _rsi(*args, **kwargs):
    from bot.features.market.finance_ta import _rsi as _fn
    return _fn(*args, **kwargs)

def _adx_approx(*args, **kwargs):
    from bot.features.market.finance_ta import _adx_approx as _fn
    return _fn(*args, **kwargs)

def _compute_ta(*args, **kwargs):
    from bot.features.market.finance_ta import _compute_ta as _fn
    return _fn(*args, **kwargs)

def _atr(*args, **kwargs):
    from bot.features.market.finance_ta import _atr as _fn
    return _fn(*args, **kwargs)

def _detect_candle_patterns(*args, **kwargs):
    from bot.features.market.finance_ta import _detect_candle_patterns as _fn
    return _fn(*args, **kwargs)

def _score_timeframe(*args, **kwargs):
    from bot.features.market.finance_ta import _score_timeframe as _fn
    return _fn(*args, **kwargs)

async def _mtf_bundle(*args, **kwargs):
    from bot.features.market.finance_ta import _mtf_bundle as _fn
    return await _fn(*args, **kwargs)

def _market_structure(*args, **kwargs):
    from bot.features.market.finance_ta import _market_structure as _fn
    return _fn(*args, **kwargs)

def _rsi_divergence(*args, **kwargs):
    from bot.features.market.finance_ta import _rsi_divergence as _fn
    return _fn(*args, **kwargs)

def _volume_breakout(*args, **kwargs):
    from bot.features.market.finance_ta import _volume_breakout as _fn
    return _fn(*args, **kwargs)

def _demand_supply_zone(*args, **kwargs):
    from bot.features.market.finance_ta import _demand_supply_zone as _fn
    return _fn(*args, **kwargs)

def _mtf_convergence(*args, **kwargs):
    from bot.features.market.finance_ta import _mtf_convergence as _fn
    return _fn(*args, **kwargs)


def _scenarios(signal, support, resistance, current, atr) -> list:
    """سناریو A/B با احتمال تقریبی"""
    lines = []
    try:
        cur = float(current) if current is not None else None
        sup = float(support) if support is not None else None
        res = float(resistance) if resistance is not None else None
        a = float(atr) if atr else None
    except Exception:
        return ["سناریو: داده ناکافی"]
    if "لانگ" in (signal or ""):
        lines.append(f"سناریو A (~۶۰٪): نگه داشتن بالای {sup or 'حمایت'} و حرکت به {res or 'مقاومت'}")
        lines.append(f"سناریو B (~۴۰٪): از دست رفتن حمایت و برگشت تا {(sup - a) if (sup and a) else 'پایین‌تر'}")
    elif "شورت" in (signal or ""):
        lines.append(f"سناریو A (~۶۰٪): رد شدن از {res or 'مقاومت'} و حرکت به {sup or 'حمایت'}")
        lines.append(f"سناریو B (~۴۰٪): شکست مقاومت و ادامه تا {(res + a) if (res and a) else 'بالاتر'}")
    else:
        lines.append("سناریو A (~۵۰٪): ادامه رنج بین حمایت و مقاومت")
        lines.append("سناریو B (~۵۰٪): شکست یکی از دو سمت با حجم و شروع روند")
    return lines


def _signal_track_stub() -> str:
    """کارنامه ساده — تا وقتی دیتابیس سیگنال نداریم"""
    return "کارنامه سیگنال: به‌زودی با ثبت خودکار ستاپ‌ها فعال می‌شود"


def _support_resistance(closes, highs, lows, current):
    if not closes:
        return None, None
    window = closes[-48:] if len(closes) >= 48 else closes
    hi_w = highs[-48:] if len(highs) >= 48 else highs
    lo_w = lows[-48:] if len(lows) >= 48 else lows
    resistance = max(hi_w) if hi_w else max(window)
    support = min(lo_w) if lo_w else min(window)
    # نزدیک‌تر کردن به قیمت فعلی با pivot ساده
    if current:
        # حمایت: بالاترین low زیر قیمت
        below = [x for x in lo_w if x < current * 0.999]
        above = [x for x in hi_w if x > current * 1.001]
        if below:
            support = max(below)
        if above:
            resistance = min(above)
    return support, resistance


def _derive_signal(ta: dict, chg_24, binance: dict, current=None, support=None, resistance=None):
    """سیگنال، امتیاز، R:R، ریسک، وضعیت اجرا — با تشخیص فرصت گذشته"""
    rsi = ta.get("rsi")
    adx = ta.get("adx") or 0
    trend = ta.get("trend") or "خنثی"
    score = 5
    signal = "خنثی / احتیاط"
    signal_emoji = "🟡"

    if trend == "صعودی":
        score += 2
        signal, signal_emoji = "لانگ", "🟢"
    elif trend == "نزولی":
        score += 2
        signal, signal_emoji = "شورت", "🔴"

    if rsi is not None:
        if signal == "لانگ" and 35 <= rsi <= 65:
            score += 1
        elif signal == "شورت" and 35 <= rsi <= 65:
            score += 1
        elif signal == "لانگ" and rsi >= 72:
            score -= 2
        elif signal == "شورت" and rsi <= 28:
            score -= 2
        elif signal == "لانگ" and rsi <= 35:
            score += 1
        elif signal == "شورت" and rsi >= 65:
            score += 1

    if adx >= 25:
        score += 1
    elif adx < 18:
        score -= 1
        if signal in ("لانگ", "شورت"):
            signal, signal_emoji = "خنثی / احتیاط", "🟡"

    if chg_24 is not None:
        if signal == "لانگ" and chg_24 < -5:
            score -= 1
        if signal == "شورت" and chg_24 > 5:
            score -= 1

    fr = (binance or {}).get("funding_rate")
    if fr is not None:
        if signal == "لانگ" and fr < 0:
            score += 1
        elif signal == "شورت" and fr > 0:
            score += 1
        elif signal == "لانگ" and fr > 0.05:
            score -= 1
        elif signal == "شورت" and fr < -0.05:
            score -= 1

    score = max(1, min(10, score))

    if score >= 8:
        rr = "خوب 🟢"
        risk = "کم 🟢"
    elif score >= 6:
        rr = "متوسط 🟡"
        risk = "متوسط 🟡"
    elif score >= 4:
        rr = "متوسط 🟡"
        risk = "متوسط 🟡"
    else:
        rr = "ضعیف 🔴"
        risk = "بالا 🔴"

    exec_status = "صبر کنید ❌"
    try:
        cur = float(current) if current is not None else None
        sup = float(support) if support is not None else None
        res = float(resistance) if resistance is not None else None
    except Exception:
        cur = sup = res = None

    if signal == "لانگ" and cur is not None and sup is not None and res is not None:
        span = max(res - sup, cur * 0.001)
        pos = (cur - sup) / span
        if pos >= 0.72:
            exec_status = "فرصت گذشته — منتظرِ موقعیتِ بعدی ⛔️"
            risk = "متوسط 🟡"
        elif pos <= 0.35 and score >= 6:
            exec_status = "قابل معامله ✅"
        elif score >= 7:
            exec_status = "با احتیاط ⚠️"
        else:
            exec_status = "صبر کنید ❌"
    elif signal == "شورت" and cur is not None and sup is not None and res is not None:
        span = max(res - sup, cur * 0.001)
        near_res = abs(res - cur) / span <= 0.35
        near_sup = abs(cur - sup) / span <= 0.28
        if near_sup:
            exec_status = "فرصت گذشته — منتظرِ موقعیتِ بعدی ⛔️"
            risk = "متوسط 🟡"
        elif near_res and score >= 6:
            exec_status = "قابل معامله ✅"
        elif score >= 7:
            exec_status = "با احتیاط ⚠️"
        else:
            exec_status = "صبر کنید ❌"
    else:
        if score >= 8:
            exec_status = "قابل معامله ✅"
        elif score >= 5:
            exec_status = "با احتیاط ⚠️"
        else:
            exec_status = "صبر کنید ❌"

    return signal, signal_emoji, score, rr, risk, exec_status



async def get_crypto_analysis_short(symbol: str) -> str:
    """نسخه کوتاه‌تر برای ابزار AI"""
    return await analyze_crypto(symbol)


# ─────────────────────────────────────────────────────────────────────────────
# منوی کامل تحلیل (شبیه Algo Analyzer)
# ─────────────────────────────────────────────────────────────────────────────


async def market_scanner(limit: int = 10) -> str:
    """اسکن سریع نمادهای برتر از نظر ستاپ MTF"""
    symbols = [
        "btc", "eth", "bnb", "sol", "xrp", "doge", "ada", "avax", "link", "dot",
        "ton", "near", "sui", "ltc", "atom", "uni", "apt", "fil", "arb", "op",
    ]
    rows = []
    for sym in symbols:
        try:
            pair = _pair_from_symbol(sym)
            mtf = await _mtf_bundle(pair)
            conv, power = _mtf_convergence(mtf)
            sc = mtf.get("scores") or {}
            di = mtf.get("dirs") or {}
            # فقط اگر force_wait نباشد و امتیاز 4H خوب باشد
            if mtf.get("force_wait"):
                continue
            score4 = sc.get("4H") or 0
            if score4 < 6:
                continue
            direction = di.get("4H") or "—"
            rows.append((power, score4, sym.upper(), direction, conv, sc))
        except Exception:
            continue
    rows.sort(key=lambda x: (x[0], x[1]), reverse=True)
    rows = rows[:limit]
    lines = [
        "🔍 اسکنر بازار — ستاپ‌های برتر",
        "────────────────────",
    ]
    if not rows:
        lines.append("الان ستاپ قوی هم‌راستا پیدا نشد (بازار رنج یا ADX ضعیف).")
    else:
        for i, (power, score4, sym, direction, conv, sc) in enumerate(rows, 1):
            lines.append(
                f"{i}. {sym} | {direction} | قدرت {power}/10 | 4H:{score4} 1H:{sc.get('1H','—')} 1D:{sc.get('1D','—')}"
            )
            lines.append(f"   {conv}")
    lines.append("")
    lines.append("⚠️ آموزشی است؛ قبل از ورود خودت تأیید کن.")
    return chr(10).join(lines)


def get_crypto_analysis_keyboard(symbol: str) -> "InlineKeyboardMarkup":
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    s = (symbol or "btc").lower().replace("usdt", "").strip()
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📅 تحلیل و نمودار روزانه", callback_data=f"cx:day:{s}"),
                InlineKeyboardButton("⏰ تحلیل و نمودار ساعتی", callback_data=f"cx:hr:{s}"),
            ],
            [
                InlineKeyboardButton("🎯 توصیه معاملاتی", callback_data=f"cx:rec:{s}"),
                InlineKeyboardButton("📡 رادار مشتقات", callback_data=f"cx:der:{s}"),
            ],
            [
                InlineKeyboardButton("🎲 ریسک و سناریوها", callback_data=f"cx:risk:{s}"),
                InlineKeyboardButton("🔍 اسکنر بازار", callback_data=f"cx:scan:{s}"),
            ],
            [
                InlineKeyboardButton("📐 سایز پوزیشن", callback_data=f"cx:pos:{s}"),
                InlineKeyboardButton("🔔 هشدار ورود", callback_data=f"cx:al:{s}"),
            ],
            [InlineKeyboardButton("🔄 بروزرسانی تحلیل", callback_data=f"cx:ref:{s}")],
        ]
    )


def _pair_from_symbol(symbol: str) -> str:
    symbol_clean = (symbol or "btc").lower().strip().replace(" ", "").replace("‌", "")
    for junk in ("تحلیل", "analyze", "ارز", "کریپتو", "usdt"):
        symbol_clean = symbol_clean.replace(junk, "")
    symbol_clean = symbol_clean.strip() or "btc"
    _sym_map = {
        "bitcoin": "BTC", "ethereum": "ETH", "binancecoin": "BNB", "solana": "SOL",
        "ripple": "XRP", "the-open-network": "TON", "dogecoin": "DOGE", "cardano": "ADA",
        "tron": "TRX", "chainlink": "LINK", "litecoin": "LTC", "polkadot": "DOT",
        "avalanche-2": "AVAX", "shiba-inu": "SHIB", "matic-network": "MATIC",
        "near": "NEAR", "pepe": "PEPE", "sui": "SUI", "btc": "BTC", "eth": "ETH",
        "sol": "SOL", "ton": "TON", "bnb": "BNB", "xrp": "XRP", "doge": "DOGE",
    }
    base = _sym_map.get(symbol_clean, symbol_clean.upper())
    if len(base) > 10:
        base = symbol_clean.upper()[:10]
    return base + "USDT"


async def trading_recommendation(symbol: str) -> str:
    """توصیه معاملاتی + حد ضرر پویا بر اساس ATR + فیلتر MTF"""
    pair = _pair_from_symbol(symbol)
    mtf = await _mtf_bundle(pair)
    binance = await _fetch_binance_futures(symbol)
    fg = await _fetch_fear_greed(7)

    ta = mtf.get("4h") or mtf.get("1h") or {}
    klines = await _fetch_klines_interval(pair, "4h", 120)
    opens, highs, lows, closes, vols = [], [], [], [], []
    for k in klines or []:
        try:
            opens.append(float(k[1]))
            highs.append(float(k[2]))
            lows.append(float(k[3]))
            closes.append(float(k[4]))
            vols.append(float(k[5]))
        except Exception:
            continue
    if len(closes) >= 30 and not ta:
        ta = _compute_ta(closes, highs, lows, vols)
        ta["atr"] = _atr(highs, lows, closes, 14)
        ta["patterns"] = _detect_candle_patterns(opens, highs, lows, closes)

    cur = closes[-1] if closes else None
    support, resistance = _support_resistance(closes, highs, lows, cur)
    signal, sem, score, rr, risk, status = _derive_signal(
        ta, None, binance or {}, current=cur, support=support, resistance=resistance
    )

    if mtf.get("force_wait"):
        signal, sem = "خنثی / احتیاط", "🟡"
        status = "صبر کنید ❌ — ADX روزانه ضعیف"
        score = min(score, 5)

    atr = ta.get("atr") or (_atr(highs, lows, closes, 14) if len(closes) > 20 else None)
    atr_mult = 1.5
    tp2 = None
    if "لانگ" in signal and support:
        entry = support
        stop = (entry - atr_mult * atr) if atr else entry * 0.985
        tp1 = resistance or ((entry + 2 * atr_mult * atr) if atr else entry * 1.03)
        tp2 = (entry + 3 * atr_mult * atr) if atr else None
    elif "شورت" in signal and resistance:
        entry = resistance
        stop = (entry + atr_mult * atr) if atr else entry * 1.015
        tp1 = support or ((entry - 2 * atr_mult * atr) if atr else entry * 0.97)
        tp2 = (entry - 3 * atr_mult * atr) if atr else None
    else:
        entry = cur
        stop = (cur - atr_mult * atr) if (cur and atr) else (cur * 0.98 if cur else None)
        tp1 = (cur + 2 * atr_mult * atr) if (cur and atr) else (cur * 1.02 if cur else None)

    def f(v):
        if v is None:
            return "—"
        try:
            v = float(v)
        except Exception:
            return "—"
        return f"{v:,.2f}" if abs(v) >= 1 else f"{v:,.6f}"

    rr_txt = rr
    try:
        if entry and stop and tp1 and entry != stop:
            risk_d = abs(float(entry) - float(stop))
            reward = abs(float(tp1) - float(entry))
            if risk_d > 0:
                rr_txt = f"{reward / risk_d:.1f} : 1"
    except Exception:
        pass

    out = [
        f"🎯 توصیه معاملاتی — {pair}",
        "────────────────────",
        f"سیگنال: {signal} {sem}",
        f"امتیاز ستاپ: {score}/10",
        f"وضعیت: {status}",
        f"ریسک: {risk} | R:R: {rr_txt}",
        "",
        "⏱ تایم‌فریم‌ها:",
    ]
    for k in ("1H", "4H", "1D"):
        out.append(
            f"  {k}: {(mtf.get('scores') or {}).get(k, '—')}/10 | {(mtf.get('dirs') or {}).get(k, '—')}"
        )
    if mtf.get("conflict"):
        out.append("⚠️ تضاد تایم‌فریم — حجم را کم کنید")
    if mtf.get("force_wait"):
        out.append("⚠️ فیلتر ADX روزانه: صبر اولویت دارد")

    out += [
        "",
        f"📍 ورود تقریبی: {f(entry)}",
        f"🛑 حد ضرر (ATR×{atr_mult}): {f(stop)}",
        f"🎯 هدف ۱: {f(tp1)}",
    ]
    if tp2:
        out.append(f"🎯 هدف ۲: {f(tp2)}")
    if atr:
        out.append(f"📐 ATR(14): {f(atr)}")
    pats = ta.get("patterns") or []
    if pats:
        out.append("🕯 الگو: " + " | ".join(pats[:2]))
    out.append("")
    out.extend(_format_fear_greed(fg))
    out.append("")
    out.append("نکته: ورود پله‌ای؛ حد ضرر را جابه‌جا نکنید.")
    out.append("⚠️ آموزشی است؛ توصیه سرمایه‌گذاری قطعی نیست.")
    return chr(10).join(out)


async def derivatives_radar(symbol: str) -> str:
    """رادار مشتقات: Funding, OI, حجم فیوچرز"""
    pair = _pair_from_symbol(symbol)
    base = pair.replace("USDT", "")
    data = await _fetch_binance_futures(symbol)
    lines = [
        f"📡 رادار مشتقات — {pair}",
        "────────────────────",
    ]
    if not data:
        lines.append("❌ داده فیوچرز در دسترس نیست (ممکن است نماد فیوچرز نداشته باشد).")
        return "\n".join(lines)

    fr = data.get("funding_rate")
    if fr is not None:
        em = "🟢" if fr > 0 else "🔴" if fr < 0 else "⚪"
        lines.append(f"Funding Rate: {em} {fr:+.4f}%")
        if fr > 0.03:
            lines.append("  → لانگ‌ها هزینه می‌دهند؛ احتمال اصلاح/فشار فروش")
        elif fr < -0.03:
            lines.append("  → شورت‌ها هزینه می‌دهند؛ احتمال اسکوییز صعودی")
        else:
            lines.append("  → فاندینگ متعادل")
    if data.get("open_interest"):
        lines.append(f"Open Interest: {data['open_interest']:,.0f}")
    if data.get("volume_24h"):
        lines.append(f"حجم فیوچرز ۲۴س: ${data['volume_24h']:,.0f}")
    if data.get("mark_price"):
        lines.append(f"Mark Price: ${data['mark_price']:,.4f}")
    if data.get("price_change_pct") is not None:
        chg = data["price_change_pct"]
        em = "🟢" if chg >= 0 else "🔴"
        lines.append(f"تغییر فیوچرز ۲۴س: {em} {chg:+.2f}%")

    ls_lines = _format_long_short(data)
    if ls_lines:
        lines.append("")
        lines.append("📊 نسبت لانگ / شورت")
        lines.extend(ls_lines)

    lines.append("")
    lines.append("منبع: Binance Futures")
    lines.append("⚠️ صرفاً اطلاعاتی است.")
    return chr(10).join(lines)


async def risk_scenarios(symbol: str) -> str:
    """سناریوهای صعودی/نزولی و ریسک"""
    pair = _pair_from_symbol(symbol)
    klines = await _fetch_klines_for_ta(pair, limit=120)
    closes, highs, lows, vols = [], [], [], []
    for k in klines or []:
        try:
            highs.append(float(k[2])); lows.append(float(k[3]))
            closes.append(float(k[4])); vols.append(float(k[5]))
        except Exception:
            continue
    if len(closes) < 20:
        return f"❌ داده کافی برای سناریوی {pair} نیست."

    cur = closes[-1]
    ta = _compute_ta(closes, highs, lows, vols)
    support, resistance = _support_resistance(closes, highs, lows, cur)
    atr = 0
    if len(highs) >= 15:
        trs = []
        for i in range(1, min(15, len(closes))):
            trs.append(max(highs[-i] - lows[-i], abs(highs[-i] - closes[-i - 1]), abs(lows[-i] - closes[-i - 1])))
        atr = sum(trs) / len(trs) if trs else cur * 0.02

    bull = resistance or (cur + atr * 2)
    bear = support or (cur - atr * 2)
    invalid = (support * 0.99) if support else (cur - atr * 3)

    def f(v):
        return f"{v:,.2f}" if v >= 1 else f"{v:,.6f}"

    lines = [
        f"🎲 ریسک و سناریوها — {pair}",
        "────────────────────",
        f"قیمت فعلی: ${f(cur)}",
        f"ATR تقریبی: ${f(atr)}",
        "",
        "🟢 سناریو صعودی:",
        f"  شکست مقاومت ~{f(bull)} می‌تواند مسیر رشد را باز کند.",
        f"  هدف بعدی تقریبی: ${f(bull + atr)}",
        "",
        "🔴 سناریو نزولی:",
        f"  از دست رفتن حمایت ~{f(bear)} فشار فروش را تشدید می‌کند.",
        f"  سطح خطرناک‌تر: ${f(invalid)}",
        "",
        f"روند فعلی سیستم: {ta.get('trend', '—')}",
        f"RSI: {ta.get('rsi', 0):.1f}" if ta.get("rsi") is not None else "RSI: —",
        "",
        "مدیریت ریسک: حداکثر ۱–۲٪ سرمایه در هر معامله پیشنهاد می‌شود.",
        "⚠️ سناریوها احتمالی‌اند؛ قطعی نیستند.",
    ]
    return "\n".join(lines)


def position_size_guide(symbol: str = "") -> str:
    pair = _pair_from_symbol(symbol) if symbol else "BTCUSDT"
    return (
        f"📐 محاسبه سایز پوزیشن — {pair}\n"
        "────────────────────\n"
        "فرمت پیام بعدی:\n"
        "`سرمایه حدضرر درصد`\n\n"
        "مثال:\n"
        "• `1000 2`  → سرمایه ۱۰۰۰ دلار، حد ضرر ۲٪\n"
        "• `5000 1.5` → سرمایه ۵۰۰۰، حد ضرر ۱.۵٪\n\n"
        "فرمول:\n"
        "ریسک دلاری = سرمایه × (درصد حدضرر / ۱۰۰)\n"
        "اگر فاصله ورود تا حدضرر را هم بفرستید:\n"
        "`سرمایه حدضرر٪ فاصله٪`\n"
        "مثال: `1000 1 2`\n"
        "حجم تقریبی = ریسک / فاصله٪"
    )


def calc_position_size(text: str) -> str:
    t = (text or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    nums = re.findall(r"[\d]+(?:\.\d+)?", t)
    if len(nums) < 2:
        return "❌ فرمت: `1000 2` یا `1000 1 2`"
    capital = float(nums[0])
    risk_pct = float(nums[1])
    risk_usd = capital * (risk_pct / 100.0)
    lines = [
        "📐 نتیجه سایز پوزیشن",
        "────────────────────",
        f"سرمایه: ${capital:,.2f}",
        f"ریسک: {risk_pct}%",
        f"حداکثر ضرر دلاری: **${risk_usd:,.2f}**",
    ]
    if len(nums) >= 3:
        dist = float(nums[2])
        if dist > 0:
            size = risk_usd / (dist / 100.0)
            lines.append(f"فاصله حدضرر: {dist}%")
            lines.append(f"حجم تقریبی پوزیشن: **${size:,.2f}**")
            lines.append("(فرض: حرکت خلاف جهت به اندازه فاصله٪)")
    lines.append("")
    lines.append("⚠️ این فقط محاسبه ریسک است، نه سیگنال ورود.")
    return "\n".join(lines)


async def entry_alert_text(symbol: str) -> str:
    pair = _pair_from_symbol(symbol)
    klines = await _fetch_klines_for_ta(pair, limit=80)
    closes, highs, lows = [], [], []
    for k in klines or []:
        try:
            highs.append(float(k[2])); lows.append(float(k[3])); closes.append(float(k[4]))
        except Exception:
            continue
    cur = closes[-1] if closes else None
    support, resistance = _support_resistance(closes, highs, lows, cur)
    ta = _compute_ta(closes, highs, lows, [1] * len(closes)) if len(closes) >= 30 else {}
    signal, _, _, _, _, _ = _derive_signal(ta, None, {})
    level = support if "لانگ" in signal else resistance
    if level is None:
        level = cur

    def f(v):
        if v is None:
            return "—"
        return f"{v:,.2f}" if v >= 1 else f"{v:,.6f}"

    return (
        f"🔔 هشدار نقطه ورود — {pair}\n"
        "────────────────────\n"
        f"قیمت فعلی: ${f(cur)}\n"
        f"سطح پیشنهادی ورود: **${f(level)}**\n"
        f"حمایت: ${f(support)} | مقاومت: ${f(resistance)}\n\n"
        "برای ثبت هشدار، قیمت هدف را بفرستید:\n"
        f"مثال: `{f(level)}`\n\n"
        "ربات وقتی نزدیک شد می‌تواند یادآوری ثبت کند.\n"
        "⚠️ مانیتورینگ لحظه‌ای ۲۴ساعته تضمینی نیست."
    )


async def register_price_alert(user_id: int, symbol: str, price: float) -> str:
    """ثبت یادآوری متنی برای قیمت هدف"""
    pair = _pair_from_symbol(symbol)
    try:
        from bot.database import add_reminder
        from datetime import datetime, timedelta
        import pytz
        # یادآوری ۱ ساعت بعد به‌عنوان یادآور بررسی قیمت (چون قیمت‌استریم نداریم)
        tz = pytz.timezone("Asia/Tehran")
        remind_at = (datetime.now(tz) + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
        text = f"🔔 بررسی قیمت {pair} — هدف شما: ${price:,.4f}"
        add_reminder(user_id, text, remind_at, repeat_type="once", repeat_every=0)
        return (
            f"✅ هشدار ثبت شد\n"
            f"{pair} → هدف ${price:,.4f}\n"
            f"یادآوری بررسی حدود: {remind_at}\n"
            "می‌توانید چند هدف دیگر هم بفرستید."
        )
    except Exception as e:
        return f"⚠️ ثبت هشدار ناموفق: {e}\nهدف شما: ${price:,.4f} برای {pair}"
