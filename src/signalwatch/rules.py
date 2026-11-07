"""Alert rules and how they are evaluated against price history.

There are two kinds of rule:

* **Level** rules (price above/below, RSI above/below, big moves) are true for
  as long as the condition holds. They alert once when they become true and
  stay quiet until they have been false again.
* **Event** rules (one line crossing another, a new high or low) happen on a
  single bar. They alert once for the bar where it happened.

Any rule can also have a ``cooldown`` such as "6h", so it alerts at most once in
that time however often its condition comes and goes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .indicators import moving_average, pct_change, rsi

LEVEL_KINDS = {"price_above", "price_below", "rsi_above", "rsi_below", "change_above", "change_below"}
CROSS_KINDS = {"cross_above", "cross_below"}
EXTREME_KINDS = {"new_high", "new_low"}
EVENT_KINDS = CROSS_KINDS | EXTREME_KINDS
KINDS = LEVEL_KINDS | EVENT_KINDS
DEFAULT_EXTREME_BARS = 20


class RuleError(ValueError):
    """A rule in the watchlist doesn't make sense."""


def parse_duration(text: str) -> int:
    """"30m", "6h", "2d" -> seconds."""
    match = re.fullmatch(r"\s*(\d+)\s*([smhd])\s*", str(text).lower())
    if not match or int(match.group(1)) == 0:
        raise RuleError(f'cooldown must look like "30m", "6h" or "1d", got {text!r}')
    return int(match.group(1)) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[match.group(2)]


@dataclass(frozen=True)
class Bar:
    """One candle. Only the close is used for now; ``time`` is an ISO date or datetime."""

    time: str
    close: float


@dataclass(frozen=True)
class Evaluation:
    active: bool
    #: For cross rules, identifies the bar the cross happened on, so it alerts only once.
    event: str | None
    message: str


@dataclass(frozen=True)
class Rule:
    kind: str
    value: float | None = None
    period: int = 14
    bars: int = 1
    line: str = "price"
    over: str | None = None
    note: str = ""
    #: Minimum seconds between two alerts from this rule (0 = no limit).
    cooldown: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Rule:
        kind = data.get("kind")
        if kind not in KINDS:
            raise RuleError(f"unknown rule kind {kind!r}; choose one of: {', '.join(sorted(KINDS))}")
        known = {"kind", "value", "period", "bars", "line", "over", "note", "cooldown"}
        extra = set(data) - known
        if extra:
            raise RuleError(f"{kind}: unknown setting(s) {', '.join(sorted(extra))}")

        value = data.get("value")
        if kind in LEVEL_KINDS:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise RuleError(f"{kind} needs a number in 'value'")
            if kind.startswith("rsi") and not 0 < value < 100:
                raise RuleError(f"{kind}: RSI 'value' must be between 0 and 100")
            if kind.startswith("change") and value <= 0:
                raise RuleError(f"{kind}: 'value' is a percentage and must be more than 0")

        period = data.get("period", 14)
        bars = data.get("bars", DEFAULT_EXTREME_BARS if kind in EXTREME_KINDS else 1)
        for name, number in (("period", period), ("bars", bars)):
            if not isinstance(number, int) or isinstance(number, bool) or number < 1:
                raise RuleError(f"{kind}: '{name}' must be a whole number of at least 1")
        if kind in EXTREME_KINDS and bars < 2:
            raise RuleError(f"{kind}: 'bars' must be at least 2 (it's how far back to look)")

        cooldown = parse_duration(data["cooldown"]) if "cooldown" in data else 0

        line = str(data.get("line", "price"))
        over = data.get("over")
        if kind in CROSS_KINDS:
            if over is None:
                raise RuleError(f'{kind} needs \'over\', e.g. over = "sma:50"')
            for spec in (line, str(over)):
                if spec != "price":
                    try:
                        moving_average(spec, [1.0])
                    except ValueError as exc:
                        raise RuleError(f"{kind}: {exc}") from None
            if line == over:
                raise RuleError(f"{kind}: 'line' and 'over' are the same, so they can never cross")

        return cls(
            kind=kind,
            value=float(value) if value is not None else None,
            period=period,
            bars=bars,
            line=line,
            over=str(over) if over is not None else None,
            note=str(data.get("note", "")),
            cooldown=cooldown,
        )

    @property
    def is_event(self) -> bool:
        """True for rules that happen on one bar (crosses, new highs/lows)."""
        return self.kind in EVENT_KINDS

    def describe(self) -> str:
        """Short human description, e.g. "RSI(14) above 70" or "price crosses above sma:200"."""
        v = self.value
        return {
            "price_above": f"price above {format_price(v)}" if v is not None else "",
            "price_below": f"price below {format_price(v)}" if v is not None else "",
            "rsi_above": f"RSI({self.period}) above {v:g}" if v is not None else "",
            "rsi_below": f"RSI({self.period}) below {v:g}" if v is not None else "",
            "change_above": f"up {v:g}% or more over {self.bars} bar(s)" if v is not None else "",
            "change_below": f"down {v:g}% or more over {self.bars} bar(s)" if v is not None else "",
            "cross_above": f"{self.line} crosses above {self.over}",
            "cross_below": f"{self.line} crosses below {self.over}",
            "new_high": f"highest close in {self.bars} bars",
            "new_low": f"lowest close in {self.bars} bars",
        }[self.kind]

    def evaluate(self, bars: list[Bar]) -> Evaluation | None:
        """Checks the rule on the latest bar. Returns None when there isn't enough history yet."""
        if not bars:
            return None
        closes = [b.close for b in bars]
        last = closes[-1]

        if self.kind in ("price_above", "price_below"):
            assert self.value is not None
            active = last > self.value if self.kind == "price_above" else last < self.value
            return Evaluation(active, None, f"price {format_price(last)} is {self.describe()}")

        if self.kind in ("rsi_above", "rsi_below"):
            assert self.value is not None
            current = rsi(closes, self.period)[-1]
            if current is None:
                return None
            active = current > self.value if self.kind == "rsi_above" else current < self.value
            return Evaluation(active, None, f"RSI({self.period}) is {current:.1f}, {self.describe()}")

        if self.kind in ("change_above", "change_below"):
            assert self.value is not None
            change = pct_change(closes, self.bars)[-1]
            if change is None:
                return None
            active = change >= self.value if self.kind == "change_above" else change <= -self.value
            return Evaluation(active, None, f"moved {change:+.2f}% over {self.bars} bar(s)")

        if self.kind in EXTREME_KINDS:
            if len(closes) < self.bars:
                return None
            earlier = closes[-self.bars:-1]
            if self.kind == "new_high":
                made = last > max(earlier)
            else:
                made = last < min(earlier)
            return Evaluation(
                made, bars[-1].time if made else None, f"price {format_price(last)} is the {self.describe()}"
            )

        # Cross rules: compare the last two bars.
        assert self.over is not None
        a = closes if self.line == "price" else moving_average(self.line, closes)
        b = closes if self.over == "price" else moving_average(self.over, closes)
        if len(closes) < 2 or None in (a[-1], a[-2], b[-1], b[-2]):
            return None
        a_prev, a_now, b_prev, b_now = a[-2], a[-1], b[-2], b[-1]
        assert a_prev is not None and a_now is not None and b_prev is not None and b_now is not None
        if self.kind == "cross_above":
            crossed = a_prev <= b_prev and a_now > b_now
        else:
            crossed = a_prev >= b_prev and a_now < b_now
        return Evaluation(
            crossed,
            bars[-1].time if crossed else None,
            f"{self.describe()} ({format_price(a_now)} vs {format_price(b_now)})",
        )


def format_price(value: float) -> str:
    """71274.08 -> "71,274.08"; small prices keep their precision (0.00001234 -> "1.234e-05")."""
    return f"{value:,.2f}" if abs(value) >= 1 else f"{value:.6g}"


@dataclass(frozen=True)
class Alert:
    symbol: str
    rule: Rule
    message: str
    price: float
    time: str

    def text(self) -> str:
        note = f" ({self.rule.note})" if self.rule.note else ""
        return f"{self.symbol}: {self.message}{note}. Last price {format_price(self.price)} at {self.time}."


def rule_id(symbol: str, rule: Rule, source: str = "", interval: str = "") -> str:
    """Stable key for remembering a rule's state between runs.

    It includes the source and interval, so the same symbol watched on two intervals
    (or from two sources) keeps separate state.
    """
    return "|".join([f"{source}:{symbol}@{interval}", *_rule_parts(rule)])


def legacy_rule_id(symbol: str, rule: Rule) -> str:
    """The key used before 0.1.1, without source and interval; read once when upgrading."""
    return "|".join([symbol, *_rule_parts(rule)])


def _rule_parts(rule: Rule) -> list[str]:
    return [rule.kind, rule.line, rule.over or "", f"{rule.value}", str(rule.period), str(rule.bars)]


def decide(
    rule: Rule, evaluation: Evaluation, previous: dict[str, Any] | None, now: float = 0.0
) -> tuple[bool, dict[str, Any]]:
    """Should this evaluation alert, given what was remembered last time? Returns (fire, new_state).

    Level rules fire when they switch from false to true. Event rules fire once per bar
    they happen on, so running every few minutes during that bar doesn't repeat the alert.
    A cooldown then holds back any alert that comes too soon after the last one.
    ``now`` is the current time in seconds since the epoch.
    """
    previous = previous or {}
    if rule.is_event:
        fire = evaluation.active and evaluation.event != previous.get("last_event")
        new_state: dict[str, Any] = {"last_event": evaluation.event if fire else previous.get("last_event")}
    else:
        fire = evaluation.active and not previous.get("active", False)
        new_state = {"active": evaluation.active}

    last_fired = previous.get("last_fired")
    if fire and rule.cooldown and isinstance(last_fired, (int, float)) and now - last_fired < rule.cooldown:
        fire = False  # too soon; the condition is still noted so it won't fire late
    if fire:
        new_state["last_fired"] = now
    elif isinstance(last_fired, (int, float)):
        new_state["last_fired"] = last_fired
    return fire, new_state
