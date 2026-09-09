import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_v33_release_and_market_speed_contract():
    release = (ROOT / "bot" / "release.py").read_text()
    assert 'VERSION = "36.0.0"' in release
    render = (ROOT / "render.yaml").read_text()
    assert "MARKET_HTTP_RETRIES" in render
    assert 'value: "36.0.0"' in render

def test_finance_parallel_market_paths_are_syntax_valid():
    for rel in (
        "bot/features/market/finance.py",
        "bot/features/market/finance_core.py",
        "bot/features/market/finance_crypto.py",
    ):
        ast.parse((ROOT / rel).read_text(), filename=rel)

def test_futures_uses_parallel_gather():
    text = (ROOT / "bot" / "features" / "market" / "finance.py").read_text()
    assert "asyncio.gather" in text
    assert 'https://fapi.binance.com/fapi/v1/premiumIndex' in text
    assert 'https://fapi.binance.com/fapi/v1/openInterest' in text

def test_analysis_has_short_lived_kline_cache():
    text = (ROOT / "bot" / "features" / "market" / "finance.py").read_text()
    assert "_HTTP_DATA_CACHE_TTL = 30" in text
    assert 'key = f"klines:{pair}:{interval}:{limit}"' in text
