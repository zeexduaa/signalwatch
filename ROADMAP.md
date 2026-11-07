# Roadmap

Where signalwatch is going: a small, dependable alert tool you can leave running.
It will stay alerts-only: no trading, no exchange keys.

Sizes are rough guesses (S = a few hours, M = about a day, L = several days, XL = a week or more).

## ✅ v0.1: the basics

- Price, RSI, percent-change and crossover rules
- Binance and Stooq price data, no API keys
- Console, Discord and Telegram alerts; secrets from the environment
- `init`, `check`, `watch`, `show`; alerts once per signal; tests on 3 OSes

## v0.2: more signals

- [ ] **MACD** rules: MACD line crossing its signal line, histogram turning positive/negative (M)
- [ ] **Bollinger Bands**: price closing outside the bands (M)
- [ ] **Volume spikes**: volume above N times its average (needs volume in bars) (M)
- [ ] **New highs and lows**: highest or lowest close in N bars (S)
- [ ] **Combine conditions** with `all = [...]` / `any = [...]` in one rule (L)
- [ ] **Cooldown** setting so a rule can't alert more than once every N hours (S)

## v0.3: reliability

- [ ] **Retries with backoff** for temporary network errors and rate limits (M)
- [ ] **Fetch each symbol once** when several rules or intervals share it (S)
- [ ] **Retry failed notifications** on the next round instead of dropping them (M)
- [ ] **Logging to a file** with `--log` and log rotation (S)
- [ ] **Validate symbols** at startup and suggest close matches for typos (M)

## v0.4: more sources and channels

- [ ] **More crypto exchanges** (Coinbase, Kraken public APIs) (M)
- [ ] **Email alerts** via SMTP (M)
- [ ] **Slack and ntfy.sh** notifications (S each)
- [ ] **Custom webhook** with a JSON template for any other service (M)

## v0.5: understanding signals

- [ ] **Backtest a rule**: `signalwatch backtest` shows when a rule would have fired over past data (L)
- [ ] **Alert history**: `signalwatch history` lists past alerts from a local log (M)
- [ ] **Charts in alerts**: attach a small price chart image to Discord/Telegram messages (L)

## v1.0: easy to run

- [ ] **Publish to PyPI** so `pip install signalwatch` works (S)
- [ ] **Docker image** and a sample docker-compose file (M)
- [ ] **Run as a service**: guides for systemd, Windows Task Scheduler and cron (S)
- [ ] **Docs site** with rule recipes (M)
