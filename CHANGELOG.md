# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- Watching the same symbol on two intervals or sources no longer shares alert state, which made one silence the other (#24). State saved by older versions is carried over.
- `signalwatch show` explains when there are no closed bars instead of crashing (#25).
- Alert messages show full prices and thresholds (`101,234.56`) instead of rounding to 6 digits (#26).

### Added

- `new_high` / `new_low` rules: the highest or lowest close in N bars (default 20).
- `cooldown` on any rule (e.g. `"6h"`), so it alerts at most once in that time.
- Rules: price above/below, RSI above/below, percent change over N bars, and line crossovers (price, `sma:N`, `ema:N`).
- Price data from Binance (crypto) and Stooq (stocks, ETFs), using closed candles only.
- Alerts to the console, Discord webhooks and Telegram bots; secrets read from the environment or `.env`.
- Commands: `init`, `check` (with `--dry-run`), `watch --every`, `show`.
- Alerts fire once per signal, remembered across restarts in `.signalwatch/state.json`.
- Tests for Linux, macOS and Windows on Python 3.11 and 3.13.
