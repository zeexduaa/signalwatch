# signalwatch

[![CI](https://github.com/zeexduaa/signalwatch/actions/workflows/ci.yml/badge.svg)](https://github.com/zeexduaa/signalwatch/actions/workflows/ci.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![No dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**Watch crypto and stock prices and get an alert when your signal fires: RSI drops below 30, price crosses its 200-day average, a coin falls 8% in a day.**

You write your signals in a small watchlist file. signalwatch checks them on a schedule using free public price data and sends you a message in the terminal, on Discord or on Telegram, once per signal, not every time it checks.

> **signalwatch only watches and notifies. It never places trades and never asks for exchange keys.** Its alerts are not financial advice.

- **Who it's for:** people who follow a few markets and don't want to stare at charts all day.
- **Built with:** Python 3.11+ standard library only (no dependencies), pytest, GitHub Actions on Linux, macOS and Windows.

> Status: **early (v0.1)**. See the [roadmap](ROADMAP.md).

## Quick start

```
pip install git+https://github.com/zeexduaa/signalwatch.git
signalwatch init            # writes watchlist.toml with examples
signalwatch check           # checks every signal once
signalwatch watch --every 15m
```

Example output (sample data):

```
$ signalwatch check
ALERT  BTCUSDT: RSI(14) is 10.2, RSI(14) below 30 (oversold). Last price 71,274.08 at 2026-10-27T00:00Z.
[07:36:35] checked 1 of 1 symbol(s), 1 alert(s)
```

Look at any symbol without a watchlist:

```
$ signalwatch show BTCUSDT
BTCUSDT (binance, 1d bars), last close 71,274.08 at 2026-10-27T00:00Z
  SMA 20   83,590.07
  SMA 50   100,594.38
  SMA 200  99,453.07
  RSI 14   10.21
  change over 1  bar(s)  -5.31%
  change over 5  bar(s)  -6.82%
  change over 20 bar(s)  -29.21%
```

## The watchlist

```toml
[settings]
interval = "1d"          # bar size: 15m ... 1w (stooq: 1d or 1w)
history = 300            # bars to download
notify = ["console"]     # add "discord" and/or "telegram"

[[watch]]
symbol = "BTCUSDT"
source = "binance"

  [[watch.rule]]
  kind = "rsi_below"
  value = 30
  note = "oversold"

  [[watch.rule]]
  kind = "cross_above"
  over = "sma:200"       # price crosses above its 200-bar average

[[watch]]
symbol = "spy.us"
source = "stooq"

  [[watch.rule]]
  kind = "price_below"
  value = 500
```

The full example is in [`examples/watchlist.toml`](examples/watchlist.toml).

### Rules

| `kind`                         | Settings                         | Fires when                                           |
|--------------------------------|----------------------------------|------------------------------------------------------|
| `price_above` / `price_below`  | `value`                          | the last close is above / below `value`              |
| `rsi_above` / `rsi_below`      | `value`, `period` (default 14)   | RSI is above / below `value`                         |
| `change_above` / `change_below`| `value` (%), `bars` (default 1)  | price moved up / down at least `value`% over `bars`  |
| `cross_above` / `cross_below`  | `over`, `line` (default `price`) | `line` crosses `over` on the latest bar              |
| `new_high` / `new_low`         | `bars` (default 20)              | the last close is the highest / lowest in `bars` bars |

`line` and `over` are `price`, `sma:N` or `ema:N`. For example, `line = "ema:12"`, `over = "ema:26"` is a classic moving-average crossover. Every rule can have a `note` that's added to its alert, and a `cooldown` such as `"30m"`, `"6h"` or `"1d"` so it alerts at most once in that time.

**When alerts repeat:** a level rule (price, RSI, change) alerts once when it becomes true and again only after it has been false. A cross or a new high/low alerts once for the bar it happened on. A `cooldown` then holds back any alert that comes too soon after the previous one. This is remembered in `.signalwatch/state.json`, so restarting doesn't resend old alerts.

### Price sources

| `source`  | Markets                              | Symbols                       | Intervals                              |
|-----------|--------------------------------------|-------------------------------|----------------------------------------|
| `binance` | crypto                               | `BTCUSDT`, `ETHUSDT`, …       | 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w  |
| `stooq`   | stocks, ETFs, indices, FX            | `aapl.us`, `spy.us`, `^spx`, … | 1d, 1w                                 |

Both are free and need no account. Only closed candles are used, so a signal doesn't flicker while a bar is still forming.

## Discord and Telegram

Secrets never go in the watchlist. Copy [`.env.example`](.env.example) to `.env` (it's git-ignored) or set the variables in your shell:

| Channel   | Variables                                                   |
|-----------|-------------------------------------------------------------|
| Discord   | `SIGNALWATCH_DISCORD_WEBHOOK` (Server Settings → Integrations → Webhooks) |
| Telegram  | `SIGNALWATCH_TELEGRAM_TOKEN` (from @BotFather), `SIGNALWATCH_TELEGRAM_CHAT_ID` |

Then add the channel to `notify` in `[settings]`.

## Commands

| Command                                  | What it does                                             |
|------------------------------------------|----------------------------------------------------------|
| `signalwatch init [-c FILE] [--force]`   | Write an example watchlist                               |
| `signalwatch check [--dry-run]`          | Check once; `--dry-run` shows what would alert, sends nothing |
| `signalwatch watch --every 15m`          | Keep checking (at most once a minute) until Ctrl+C       |
| `signalwatch show SYMBOL [--source stooq] [--interval 4h]` | Latest price, SMA 20/50/200, RSI and changes |

Exit codes: `0` ok, `1` no symbol could be fetched, `2` a problem with the watchlist or notification settings.

## Development

```
git clone https://github.com/zeexduaa/signalwatch.git
cd signalwatch
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

```
src/signalwatch/
  indicators.py   SMA, EMA, RSI, percent change
  rules.py        rule types, evaluation, when to alert
  providers.py    Binance and Stooq price data
  notify.py       console, Discord, Telegram; .env loading
  config.py       the watchlist file
  engine.py       one round of checking; saved state
  cli.py          the commands
```

Network calls are kept apart from parsing, so the tests run offline against saved responses.

## License

[MIT](LICENSE) © 2026 Syed Ali
