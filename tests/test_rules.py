import pytest

from signalwatch.rules import Alert, Bar, Rule, RuleError, decide, format_price, rule_id


def bars(*closes, start=1):
    return [Bar(f"2026-01-{i:02d}", float(c)) for i, c in enumerate(closes, start)]


def test_price_rules():
    above = Rule.from_dict({"kind": "price_above", "value": 100})
    assert above.evaluate(bars(99, 101)).active
    assert not above.evaluate(bars(101, 100)).active
    below = Rule.from_dict({"kind": "price_below", "value": 50})
    assert below.evaluate(bars(49.5)).active


def test_rsi_rule_needs_history():
    rule = Rule.from_dict({"kind": "rsi_above", "value": 70, "period": 3})
    assert rule.evaluate(bars(1, 2, 3)) is None
    ev = rule.evaluate(bars(1, 2, 3, 4))
    assert ev is not None and ev.active
    assert "RSI(3) is 100.0" in ev.message


def test_change_rules():
    up = Rule.from_dict({"kind": "change_above", "value": 5, "bars": 2})
    assert up.evaluate(bars(100, 101, 106)).active
    assert not up.evaluate(bars(100, 101, 104)).active
    down = Rule.from_dict({"kind": "change_below", "value": 10})
    assert down.evaluate(bars(100, 89)).active
    assert not down.evaluate(bars(100, 95)).active
    assert down.evaluate(bars(100)) is None


def test_price_crossing_a_moving_average():
    rule = Rule.from_dict({"kind": "cross_above", "over": "sma:3"})
    # sma:3 of (10,10,10)=10 then (10,10,13)=11; price goes 10 -> 13, crossing above.
    ev = rule.evaluate(bars(10, 10, 10, 13))
    assert ev is not None and ev.active and ev.event == "2026-01-04"
    # Already above on both bars: no new cross.
    assert not rule.evaluate(bars(10, 10, 10, 13, 15)).active


def test_golden_and_death_cross():
    golden = Rule.from_dict({"kind": "cross_above", "line": "sma:2", "over": "sma:4"})
    death = Rule.from_dict({"kind": "cross_below", "line": "sma:2", "over": "sma:4"})
    rising = bars(5, 4, 3, 2, 3, 6)
    assert golden.evaluate(rising).active
    assert not death.evaluate(rising).active
    falling = bars(1, 2, 3, 4, 3, 0)
    assert death.evaluate(falling).active


def test_cross_needs_enough_history():
    rule = Rule.from_dict({"kind": "cross_above", "over": "sma:5"})
    assert rule.evaluate(bars(1, 2, 3, 4, 5)) is None


@pytest.mark.parametrize(
    "data, message",
    [
        ({"kind": "moon"}, "unknown rule kind"),
        ({"kind": "price_above"}, "needs a number"),
        ({"kind": "price_above", "value": True}, "needs a number"),
        ({"kind": "rsi_above", "value": 120}, "between 0 and 100"),
        ({"kind": "change_above", "value": -3}, "more than 0"),
        ({"kind": "rsi_below", "value": 30, "period": 0}, "'period'"),
        ({"kind": "cross_above"}, "needs 'over'"),
        ({"kind": "cross_above", "over": "wma:3"}, "moving average"),
        ({"kind": "cross_above", "line": "sma:5", "over": "sma:5"}, "can never cross"),
        ({"kind": "price_above", "value": 1, "colour": "red"}, "unknown setting"),
    ],
)
def test_bad_rules_are_explained(data, message):
    with pytest.raises(RuleError, match=message):
        Rule.from_dict(data)


def test_level_rules_alert_once_until_they_reset():
    rule = Rule.from_dict({"kind": "price_above", "value": 100})
    state = None
    fired = []
    for close in (99, 101, 102, 103, 98, 104):
        ev = rule.evaluate(bars(close))
        fire, state = decide(rule, ev, state)
        fired.append(fire)
    assert fired == [False, True, False, False, False, True]


def test_cross_rules_alert_once_per_bar():
    rule = Rule.from_dict({"kind": "cross_above", "over": "sma:3"})
    history = bars(10, 10, 10, 13)
    ev = rule.evaluate(history)
    fire1, state = decide(rule, ev, None)
    fire2, state = decide(rule, rule.evaluate(history), state)  # same bar, checked again
    assert (fire1, fire2) == (True, False)
    assert state == {"last_event": "2026-01-04"}


def test_rule_id_and_alert_text():
    rule = Rule.from_dict({"kind": "rsi_below", "value": 30, "note": "oversold"})
    assert rule_id("BTCUSDT", rule) != rule_id("ETHUSDT", rule)
    alert = Alert("BTCUSDT", rule, "RSI(14) is 28.4, RSI(14) below 30", 61000.5, "2026-11-07")
    assert alert.text() == "BTCUSDT: RSI(14) is 28.4, RSI(14) below 30 (oversold). Last price 61,000.50 at 2026-11-07."


def test_describe():
    assert Rule.from_dict({"kind": "cross_below", "line": "ema:12", "over": "sma:26"}).describe() == (
        "ema:12 crosses below sma:26"
    )
    assert Rule.from_dict({"kind": "change_above", "value": 7.5, "bars": 3}).describe() == (
        "up 7.5% or more over 3 bar(s)"
    )


def test_format_price():
    assert format_price(71274.084) == "71,274.08"
    assert format_price(1) == "1.00"
    assert format_price(0.00001234) == "1.234e-05"
    assert format_price(0.5) == "0.5"
