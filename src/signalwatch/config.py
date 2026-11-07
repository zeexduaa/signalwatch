"""Reading the watchlist file (TOML)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .notify import CHANNELS
from .providers import SOURCES
from .rules import Rule, RuleError

DEFAULT_PATH = "watchlist.toml"

EXAMPLE = '''\
# signalwatch watchlist. Run `signalwatch check` to test it once,
# or `signalwatch watch --every 15m` to keep checking.
#
# signalwatch only watches prices and sends alerts. It never trades.

[settings]
interval = "1d"          # bar size: 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w (stooq: 1d or 1w)
history = 300            # how many bars to download (enough for a 200-bar average)
notify = ["console"]     # add "discord" and/or "telegram" (see .env.example)

[[watch]]
symbol = "BTCUSDT"
source = "binance"

  [[watch.rule]]
  kind = "rsi_below"
  value = 30
  note = "oversold"

  [[watch.rule]]
  kind = "cross_above"   # price crosses above its 200-day average
  over = "sma:200"

[[watch]]
symbol = "ETHUSDT"
source = "binance"
interval = "4h"          # this symbol uses 4-hour bars

  [[watch.rule]]
  kind = "cross_above"   # "golden cross" of two averages
  line = "ema:12"
  over = "ema:26"

  [[watch.rule]]
  kind = "change_below"
  value = 8
  bars = 6               # down 8% or more over the last 6 bars (one day)

[[watch]]
symbol = "spy.us"
source = "stooq"

  [[watch.rule]]
  kind = "price_below"
  value = 500
'''


class ConfigError(ValueError):
    pass


@dataclass
class Watch:
    symbol: str
    source: str
    interval: str
    rules: list[Rule]


@dataclass
class Config:
    watches: list[Watch]
    history: int = 300
    notify: list[str] = field(default_factory=lambda: ["console"])


def _settings(raw: dict[str, Any], where: str) -> tuple[str, int, list[str]]:
    unknown = set(raw) - {"interval", "history", "notify"}
    if unknown:
        raise ConfigError(f"{where}: unknown setting(s) in [settings]: {', '.join(sorted(unknown))}")
    interval = raw.get("interval", "1d")
    history = raw.get("history", 300)
    notify = raw.get("notify", ["console"])
    if not isinstance(history, int) or isinstance(history, bool) or not 2 <= history <= 1000:
        raise ConfigError(f"{where}: history must be a whole number from 2 to 1000")
    if isinstance(notify, str):
        notify = [notify]
    if not isinstance(notify, list) or not notify or not all(isinstance(n, str) for n in notify):
        raise ConfigError(f'{where}: notify must be a list like ["console", "discord"]')
    bad = [n for n in notify if n not in CHANNELS]
    if bad:
        raise ConfigError(f"{where}: unknown notify channel(s) {', '.join(bad)}; choose from {', '.join(CHANNELS)}")
    return str(interval), history, list(dict.fromkeys(notify))


def parse_config(text: str, where: str = DEFAULT_PATH) -> Config:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{where}: not valid TOML: {exc}") from None

    unknown = set(data) - {"settings", "watch"}
    if unknown:
        raise ConfigError(f"{where}: unknown section(s): {', '.join(sorted(unknown))}")
    default_interval, history, notify = _settings(data.get("settings", {}), where)

    raw_watches = data.get("watch", [])
    if not isinstance(raw_watches, list) or not raw_watches:
        raise ConfigError(f"{where}: add at least one [[watch]] entry")

    watches = []
    for n, raw in enumerate(raw_watches, 1):
        label = f"{where}: watch #{n}"
        unknown = set(raw) - {"symbol", "source", "interval", "rule"}
        if unknown:
            raise ConfigError(f"{label}: unknown setting(s) {', '.join(sorted(unknown))}")
        symbol = raw.get("symbol")
        if not isinstance(symbol, str) or not symbol.strip():
            raise ConfigError(f"{label}: needs a symbol, e.g. symbol = \"BTCUSDT\"")
        symbol = symbol.strip()
        label = f"{where}: {symbol}"
        source = raw.get("source", "binance")
        if source not in SOURCES:
            raise ConfigError(f"{label}: source must be {' or '.join(sorted(SOURCES))}")
        interval = str(raw.get("interval", default_interval))
        if interval not in SOURCES[source]:
            allowed = ", ".join(sorted(SOURCES[source]))
            raise ConfigError(f"{label}: {source} doesn't offer {interval!r} bars; choose one of: {allowed}")
        raw_rules = raw.get("rule", [])
        if not isinstance(raw_rules, list) or not raw_rules:
            raise ConfigError(f"{label}: add at least one [[watch.rule]]")
        rules = []
        for r, raw_rule in enumerate(raw_rules, 1):
            try:
                rules.append(Rule.from_dict(raw_rule))
            except RuleError as exc:
                raise ConfigError(f"{label}, rule #{r}: {exc}") from None
        watches.append(Watch(symbol, source, interval, rules))
    return Config(watches=watches, history=history, notify=notify)


def load_config(path: str | Path = DEFAULT_PATH) -> Config:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"{path} not found. Create one with `signalwatch init`.") from None
    return parse_config(text, str(path))
