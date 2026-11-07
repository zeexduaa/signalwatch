"""Where prices come from. Both sources are free and need no account or API key.

* ``binance``: crypto pairs such as BTCUSDT, from Binance's public market data.
* ``stooq``: stocks, ETFs and indices such as aapl.us or spy.us, daily or weekly, from Stooq.

Parsing is kept separate from downloading so it can be tested with saved responses.
"""

from __future__ import annotations

import csv
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone

from . import __version__
from .rules import Bar

USER_AGENT = f"signalwatch/{__version__} (+https://github.com/zeexduaa/signalwatch)"
TIMEOUT = 15

BINANCE_INTERVALS = {"15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"}
STOOQ_INTERVALS = {"1d": "d", "1w": "w"}
SOURCES = {"binance": BINANCE_INTERVALS, "stooq": set(STOOQ_INTERVALS)}


class ProviderError(Exception):
    """Prices couldn't be fetched or understood."""


Fetcher = Callable[[str], str]


def http_get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200]
        raise ProviderError(f"HTTP {exc.code} from {urllib.parse.urlsplit(url).netloc}: {detail}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise ProviderError(f"could not reach {urllib.parse.urlsplit(url).netloc}: {reason}") from None


# ---- Binance -------------------------------------------------------------------------------


def binance_url(symbol: str, interval: str, limit: int) -> str:
    query = urllib.parse.urlencode({"symbol": symbol.upper(), "interval": interval, "limit": min(limit, 1000)})
    return f"https://api.binance.com/api/v3/klines?{query}"


def parse_binance(text: str, now_ms: int | None = None) -> list[Bar]:
    """Turns Binance klines into bars, leaving out the candle that hasn't closed yet."""
    try:
        rows = json.loads(text)
    except json.JSONDecodeError:
        raise ProviderError("Binance sent something that isn't JSON") from None
    if isinstance(rows, dict):  # error responses look like {"code": -1121, "msg": "Invalid symbol."}
        raise ProviderError(f"Binance: {rows.get('msg', rows)}")
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    bars = []
    try:
        for row in rows:
            close_time = int(row[6])
            if close_time > now_ms:
                continue  # still forming: its close would change on every check
            opened = datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc)
            bars.append(Bar(opened.strftime("%Y-%m-%dT%H:%MZ"), float(row[4])))
    except (TypeError, ValueError, IndexError):
        raise ProviderError("Binance sent price data in an unexpected format") from None
    return bars


# ---- Stooq ---------------------------------------------------------------------------------


def stooq_url(symbol: str, interval: str) -> str:
    query = urllib.parse.urlencode({"s": symbol.lower(), "i": STOOQ_INTERVALS[interval]})
    return f"https://stooq.com/q/d/l/?{query}"


def parse_stooq(text: str) -> list[Bar]:
    """Turns Stooq's CSV (Date,Open,High,Low,Close,Volume) into bars."""
    stripped = text.strip()
    if not stripped or stripped.lower().startswith("no data"):
        raise ProviderError("Stooq has no data for that symbol (stocks need a market suffix, e.g. aapl.us)")
    reader = csv.DictReader(io.StringIO(stripped))
    if reader.fieldnames is None or "Close" not in reader.fieldnames or "Date" not in reader.fieldnames:
        raise ProviderError("Stooq sent data in an unexpected format")
    bars = []
    for row in reader:
        try:
            bars.append(Bar(row["Date"], float(row["Close"])))
        except (TypeError, ValueError):
            continue  # skip a damaged line rather than failing the whole symbol
    if not bars:
        raise ProviderError("Stooq returned no prices")
    return bars


# ---- Entry point ---------------------------------------------------------------------------


def fetch_bars(source: str, symbol: str, interval: str, history: int, get: Fetcher | None = None) -> list[Bar]:
    """The last ``history`` closed bars for ``symbol``, oldest first."""
    get = get or http_get
    if source not in SOURCES:
        raise ProviderError(f"unknown source {source!r}; choose {' or '.join(sorted(SOURCES))}")
    if interval not in SOURCES[source]:
        allowed = ", ".join(sorted(SOURCES[source]))
        raise ProviderError(f"{source} doesn't offer {interval!r} bars; choose one of: {allowed}")
    if source == "binance":
        bars = parse_binance(get(binance_url(symbol, interval, history + 1)))
    else:
        bars = parse_stooq(get(stooq_url(symbol, interval)))
    return bars[-history:]
