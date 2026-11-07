"""Command-line interface.

    signalwatch init                 write an example watchlist.toml
    signalwatch check                check every rule once and send alerts
    signalwatch watch --every 15m    keep checking on a schedule
    signalwatch show BTCUSDT         print the latest price and indicators for one symbol
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from . import __version__
from .config import DEFAULT_PATH, EXAMPLE, ConfigError, load_config
from .engine import DEFAULT_STATE, load_state, run_round, save_state
from .indicators import pct_change, rsi, sma
from .notify import NotifyError, build_notifiers, load_dotenv
from .providers import SOURCES, ProviderError, fetch_bars

DISCLAIMER = "signalwatch sends alerts only. It never places trades, and its alerts are not financial advice."


def parse_every(text: str) -> int:
    """'90s', '15m', '1h' -> seconds. At least 60 seconds, to be kind to the free price APIs."""
    match = re.fullmatch(r"\s*(\d+)\s*([smh])\s*", text.lower())
    if not match:
        raise argparse.ArgumentTypeError("use a number and a unit, like 30s, 15m or 1h")
    seconds = int(match.group(1)) * {"s": 1, "m": 60, "h": 3600}[match.group(2)]
    if seconds < 60:
        raise argparse.ArgumentTypeError("check at most once a minute (--every 1m or more)")
    return seconds


def _stamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _one_round(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    notifiers = [] if args.dry_run else build_notifiers(config.notify)
    state = load_state(args.state)
    result = run_round(config, state, notifiers, dry_run=args.dry_run)
    if not args.dry_run:
        save_state(args.state, state)

    if args.dry_run:
        for alert in result.alerts:
            print(f"WOULD ALERT  {alert.text()}")
    for symbol, error in result.errors.items():
        print(f"[{_stamp()}] {symbol}: {error}", file=sys.stderr)
    for name, error in result.send_errors.items():
        print(f"[{_stamp()}] could not send to {name}: {error}", file=sys.stderr)
    print(f"[{_stamp()}] checked {result.checked} of {len(config.watches)} symbol(s), {len(result.alerts)} alert(s)")
    return 1 if result.checked == 0 else 0


def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.config)
    if path.exists() and not args.force:
        print(f"{path} already exists (use --force to overwrite)", file=sys.stderr)
        return 1
    path.write_text(EXAMPLE, encoding="utf-8")
    print(f"Wrote {path}. Edit it, then run: signalwatch check")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    return _one_round(args)


def cmd_watch(args: argparse.Namespace) -> int:
    print(f"Checking every {args.every // 60} minute(s). Press Ctrl+C to stop.\n{DISCLAIMER}")
    try:
        while True:
            try:
                _one_round(args)
            except (ConfigError, NotifyError) as exc:
                # The watchlist may be mid-edit; report and try again next round.
                print(f"[{_stamp()}] {exc}", file=sys.stderr)
            time.sleep(args.every)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


def cmd_show(args: argparse.Namespace) -> int:
    bars = fetch_bars(args.source, args.symbol, args.interval, 300)
    if not bars:
        raise ProviderError(f"no closed {args.interval} bars for {args.symbol.upper()} yet")
    closes = [b.close for b in bars]
    last = bars[-1]

    def fmt(value: float | None, suffix: str = "") -> str:
        if value is None:
            return "not enough history"
        return f"{value:,.2f}{suffix}" if abs(value) >= 1 or suffix else f"{value:.6g}"

    print(f"{args.symbol.upper()} ({args.source}, {args.interval} bars), last close {fmt(last.close)} at {last.time}")
    for period in (20, 50, 200):
        print(f"  SMA {period:<4} {fmt(sma(closes, period)[-1])}")
    print(f"  RSI 14   {fmt(rsi(closes, 14)[-1])}")
    for n in (1, 5, 20):
        print(f"  change over {n:<2} bar(s)  {fmt(pct_change(closes, n)[-1] if len(closes) > n else None, '%')}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="signalwatch",
        description="Watch market prices and get alerts when your signals fire. " + DISCLAIMER,
    )
    parser.add_argument("--version", action="version", version=f"signalwatch {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def with_config(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
        p.add_argument("-c", "--config", default=DEFAULT_PATH, help=f"watchlist file (default: {DEFAULT_PATH})")
        return p

    p = with_config(sub.add_parser("init", help="write an example watchlist"))
    p.add_argument("--force", action="store_true", help="overwrite an existing file")
    p.set_defaults(func=cmd_init)

    for name, func, help_text in (
        ("check", cmd_check, "check every rule once and send alerts"),
        ("watch", cmd_watch, "keep checking on a schedule"),
    ):
        p = with_config(sub.add_parser(name, help=help_text))
        p.add_argument("--state", default=DEFAULT_STATE, help=f"where to remember alerts (default: {DEFAULT_STATE})")
        p.add_argument("--dry-run", action="store_true", help="show what would alert without sending or remembering")
        if name == "watch":
            p.add_argument("--every", type=parse_every, default=parse_every("15m"), help="how often, e.g. 5m or 1h")
        p.set_defaults(func=func)

    p = sub.add_parser("show", help="print the latest price and indicators for one symbol")
    p.add_argument("symbol")
    p.add_argument("--source", choices=sorted(SOURCES), default="binance")
    p.add_argument("--interval", default="1d")
    p.set_defaults(func=cmd_show)
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, NotifyError, ProviderError) as exc:
        print(f"signalwatch: {exc}", file=sys.stderr)
        return 2
