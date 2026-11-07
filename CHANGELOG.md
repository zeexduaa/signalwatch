# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Rules: price above/below, RSI above/below, percent change over N bars, and line crossovers (price, `sma:N`, `ema:N`).
- Price data from Binance (crypto) and Stooq (stocks, ETFs), using closed candles only.
- Alerts to the console, Discord webhooks and Telegram bots; secrets read from the environment or `.env`.
- Commands: `init`, `check` (with `--dry-run`), `watch --every`, `show`.
- Alerts fire once per signal, remembered across restarts in `.signalwatch/state.json`.
- Tests for Linux, macOS and Windows on Python 3.11 and 3.13.
