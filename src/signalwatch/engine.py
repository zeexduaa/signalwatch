"""One round of checking: fetch prices, evaluate rules, decide what to alert, remember state."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Config
from .notify import NotifyError, Notifier
from .providers import Fetcher, ProviderError, fetch_bars
from .rules import Alert, decide, rule_id

DEFAULT_STATE = ".signalwatch/state.json"


def load_state(path: str | Path) -> dict[str, Any]:
    """What each rule looked like last time. A missing or damaged file means a fresh start."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    rules = data.get("rules") if isinstance(data, dict) else None
    return rules if isinstance(rules, dict) else {}


def save_state(path: str | Path, rules: dict[str, Any]) -> None:
    """Writes atomically, so a crash mid-write can't leave a half-written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".state-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "rules": rules}, fh, indent=2, sort_keys=True)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


@dataclass
class RoundResult:
    alerts: list[Alert] = field(default_factory=list)
    #: symbol -> what went wrong fetching it
    errors: dict[str, str] = field(default_factory=dict)
    #: notifier name -> what went wrong sending
    send_errors: dict[str, str] = field(default_factory=dict)
    checked: int = 0


def run_round(
    config: Config,
    state: dict[str, Any],
    notifiers: list[Notifier],
    get: Fetcher | None = None,
    dry_run: bool = False,
) -> RoundResult:
    """Checks every watch once and sends alerts. Updates ``state`` in place.

    One symbol failing to download doesn't stop the others, and one notifier failing
    doesn't stop the rest. With ``dry_run`` nothing is sent and ``state`` is unchanged.
    """
    result = RoundResult()
    for watch in config.watches:
        try:
            bars = fetch_bars(watch.source, watch.symbol, watch.interval, config.history, get)
        except ProviderError as exc:
            result.errors[watch.symbol] = str(exc)
            continue
        if not bars:
            result.errors[watch.symbol] = "no closed bars yet"
            continue
        result.checked += 1
        last = bars[-1]
        for rule in watch.rules:
            evaluation = rule.evaluate(bars)
            if evaluation is None:
                continue  # not enough history for this rule yet
            key = rule_id(watch.symbol, rule)
            fire, new_state = decide(rule, evaluation, state.get(key))
            if not dry_run:
                state[key] = new_state
            if fire:
                result.alerts.append(Alert(watch.symbol, rule, evaluation.message, last.close, last.time))

    if not dry_run:
        for alert in result.alerts:
            for notifier in notifiers:
                try:
                    notifier.send(alert.text())
                except NotifyError as exc:
                    result.send_errors[notifier.name] = str(exc)
    return result
