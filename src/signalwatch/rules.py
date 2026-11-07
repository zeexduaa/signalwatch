"""Alert rules and how they are evaluated against price history.

There are two kinds of rule:

* **Level** rules (price above/below, RSI above/below, big moves) are true for
  as long as the condition holds. They alert once when they become true and
  stay quiet until they have been false again.
* **Cross** rules (one line crossing another) are events on a single bar. They
  alert once for the bar where the cross happened.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .indicators import moving_average, pct_change, rsi

LEVEL_KINDS = {"price_above", "price_below", "rsi_above", "rsi_below", "change_above", "change_below"}
CROSS_KINDS = {"cross_above", "cross_below"}
KINDS = LEVEL_KINDS | CROSS_KINDS


class RuleError(ValueError):
    """A rule in the watchlist doesn't make sense."""


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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Rule:
        kind = data.get("kind")
        if kind not in KINDS:
            raise RuleError(f"unknown rule kind {kind!r}; choose one of: {', '.join(sorted(KINDS))}")
        known = {"kind", "value", "period", "bars", "line", "over", "note"}
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
        bars = data.get("bars", 1)
        for name, number in (("period", period), ("bars", bars)):
            if not isinstance(number, int) or isinstance(number, bool) or number < 1:
                raise RuleError(f"{kind}: '{name}' must be a whole number of at least 1")

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
        )

    @property
    def is_cross(self) -> bool:
        return self.kind in CROSS_KINDS

    def describe(self) -> str:
        """Short human description, e.g. "RSI(14) above 70" or "price crosses above sma:200"."""
        v = self.value
        return {
            "price_above": f"price above {v:g}" if v is not None else "",
            "price_below": f"price below {v:g}" if v is not None else "",
            "rsi_above": f"RSI({self.period}) above {v:g}" if v is not None else "",
            "rsi_below": f"RSI({self.period}) below {v:g}" if v is not None else "",
            "change_above": f"up {v:g}% or more over {self.bars} bar(s)" if v is not None else "",
            "change_below": f"down {v:g}% or more over {self.bars} bar(s)" if v is not None else "",
            "cross_above": f"{self.line} crosses above {self.over}",
            "cross_below": f"{self.line} crosses below {self.over}",
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
            return Evaluation(active, None, f"price {last:g} is {self.describe()}")

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
            f"{self.describe()} ({a_now:g} vs {b_now:g})",
        )


@dataclass(frozen=True)
class Alert:
    symbol: str
    rule: Rule
    message: str
    price: float
    time: str

    def text(self) -> str:
        note = f" ({self.rule.note})" if self.rule.note else ""
        return f"{self.symbol}: {self.message}{note}. Last price {self.price:g} at {self.time}."


def rule_id(symbol: str, rule: Rule) -> str:
    """Stable key for remembering a rule's state between runs."""
    parts = [symbol, rule.kind, rule.line, rule.over or "", f"{rule.value}", str(rule.period), str(rule.bars)]
    return "|".join(parts)


def decide(rule: Rule, evaluation: Evaluation, previous: dict[str, Any] | None) -> tuple[bool, dict[str, Any]]:
    """Should this evaluation alert, given what was remembered last time? Returns (fire, new_state).

    Level rules fire when they switch from false to true. Cross rules fire once per bar
    they cross on, so running every few minutes during that bar doesn't repeat the alert.
    """
    previous = previous or {}
    if rule.is_cross:
        fire = evaluation.active and evaluation.event != previous.get("last_event")
        return fire, {"last_event": evaluation.event if fire else previous.get("last_event")}
    fire = evaluation.active and not previous.get("active", False)
    return fire, {"active": evaluation.active}
