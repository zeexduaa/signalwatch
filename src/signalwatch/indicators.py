"""Technical indicators on a list of closing prices.

Every function returns a list the same length as its input, with ``None``
where there isn't enough history yet, so results line up bar by bar.
"""

from __future__ import annotations

from collections.abc import Sequence

Series = list[float | None]


def _check_period(period: int) -> None:
    if not isinstance(period, int) or period < 1:
        raise ValueError(f"period must be a positive whole number, got {period!r}")


def sma(values: Sequence[float], period: int) -> Series:
    """Simple moving average: the mean of the last ``period`` values."""
    _check_period(period)
    out: Series = [None] * len(values)
    total = 0.0
    for i, v in enumerate(values):
        total += v
        if i >= period:
            total -= values[i - period]
        if i >= period - 1:
            out[i] = total / period
    return out


def ema(values: Sequence[float], period: int) -> Series:
    """Exponential moving average, seeded with the SMA of the first ``period`` values."""
    _check_period(period)
    out: Series = [None] * len(values)
    if len(values) < period:
        return out
    k = 2 / (period + 1)
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(values: Sequence[float], period: int = 14) -> Series:
    """Relative Strength Index (0-100) using Wilder's smoothing, as most charting tools do."""
    _check_period(period)
    out: Series = [None] * len(values)
    if len(values) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    avg_gain, avg_loss = gains / period, losses / period
    out[period] = _rsi_value(avg_gain, avg_loss)
    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(change, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-change, 0.0)) / period
        out[i] = _rsi_value(avg_gain, avg_loss)
    return out


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def pct_change(values: Sequence[float], bars: int = 1) -> Series:
    """Percent change versus ``bars`` bars ago (5.0 means +5%)."""
    _check_period(bars)
    out: Series = [None] * len(values)
    for i in range(bars, len(values)):
        before = values[i - bars]
        if before != 0:
            out[i] = (values[i] - before) / before * 100
    return out


def moving_average(spec: str, values: Sequence[float]) -> Series:
    """Parses "sma:50" or "ema:12" and computes it. Raises ValueError for anything else."""
    kind, _, period_text = spec.strip().lower().partition(":")
    if kind not in ("sma", "ema") or not period_text.isdigit() or int(period_text) < 1:
        raise ValueError(f'moving average must look like "sma:50" or "ema:12", got {spec!r}')
    period = int(period_text)
    return sma(values, period) if kind == "sma" else ema(values, period)
