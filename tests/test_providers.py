from pathlib import Path

import pytest

from signalwatch import providers
from signalwatch.providers import ProviderError, binance_url, fetch_bars, parse_binance, parse_stooq, stooq_url

FIXTURES = Path(__file__).parent / "fixtures"
BINANCE = (FIXTURES / "binance_klines.json").read_text()
STOOQ = (FIXTURES / "stooq_spy.csv").read_text()
DAY = 86_400_000
START = 1_793_836_800_000


def test_parse_binance_keeps_closed_candles_only():
    # "Now" is during the third day, so its candle hasn't closed and must be left out.
    bars = parse_binance(BINANCE, now_ms=START + 2 * DAY + 5_000)
    assert [b.close for b in bars] == [68010.5, 68420.0]
    assert bars[0].time == "2026-11-05T00:00Z"
    assert len(parse_binance(BINANCE, now_ms=START + 10 * DAY)) == 3


@pytest.mark.parametrize(
    "text, message",
    [
        ('{"code": -1121, "msg": "Invalid symbol."}', "Invalid symbol"),
        ("<html>oops</html>", "isn't JSON"),
        ('[["x"]]', "unexpected format"),
    ],
)
def test_parse_binance_errors(text, message):
    with pytest.raises(ProviderError, match=message):
        parse_binance(text, now_ms=0)


def test_parse_stooq():
    bars = parse_stooq(STOOQ)
    assert [b.time for b in bars] == ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]
    assert bars[-1].close == 567.10


def test_parse_stooq_skips_damaged_lines():
    text = "Date,Open,High,Low,Close,Volume\n2026-11-03,1,1,1,oops,1\n2026-11-04,1,1,1,9.5,1\n"
    assert [b.close for b in parse_stooq(text)] == [9.5]


@pytest.mark.parametrize("text", ["", "No data", "Date,Open\n2026-01-01,1\n", "Date,Close\n"])
def test_parse_stooq_errors(text):
    with pytest.raises(ProviderError):
        parse_stooq(text)


def test_urls():
    assert binance_url("btcusdt", "4h", 5000) == (
        "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=4h&limit=1000"
    )
    assert stooq_url("SPY.US", "1w") == "https://stooq.com/q/d/l/?s=spy.us&i=w"


def test_fetch_bars_trims_history_and_uses_the_right_url():
    seen = []

    def fake_get(url):
        seen.append(url)
        return STOOQ

    bars = fetch_bars("stooq", "spy.us", "1d", 2, get=fake_get)
    assert [b.close for b in bars] == [574.65, 567.10]
    assert seen == ["https://stooq.com/q/d/l/?s=spy.us&i=d"]


def test_fetch_bars_uses_http_get_by_default(monkeypatch):
    monkeypatch.setattr(providers, "http_get", lambda url: STOOQ)
    assert len(fetch_bars("stooq", "spy.us", "1d", 10)) == 4


@pytest.mark.parametrize(
    "source, interval, message",
    [("kraken", "1d", "unknown source"), ("stooq", "4h", "doesn't offer"), ("binance", "3d", "doesn't offer")],
)
def test_fetch_bars_rejects_bad_sources_and_intervals(source, interval, message):
    with pytest.raises(ProviderError, match=message):
        fetch_bars(source, "X", interval, 10, get=lambda url: "")
