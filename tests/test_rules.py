import pytest

from signalwatch.rules import (
    Alert,
    Bar,
    Rule,
    RuleError,
    decide,
    format_price,
    legacy_rule_id,
    parse_duration,
    rule_id,
)


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
        ({"kind": "new_high", "bars": 1}, "at least 2"),
        ({"kind": "price_above", "value": 1, "cooldown": "soon"}, "cooldown must look like"),
        ({"kind": "price_above", "value": 1, "cooldown": "0h"}, "cooldown must look like"),
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
    assert state["last_event"] == "2026-01-04"


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


def test_new_high_and_low():
    high = Rule.from_dict({"kind": "new_high", "bars": 4})
    low = Rule.from_dict({"kind": "new_low", "bars": 4})
    assert high.bars == 4 and high.is_event
    ev = high.evaluate(bars(5, 3, 4, 6))
    assert ev is not None and ev.active and ev.event == "2026-01-04"
    assert ev.message == "price 6.00 is the highest close in 4 bars"
    assert not high.evaluate(bars(5, 3, 4, 5)).active  # equal to the old high isn't a new one
    assert low.evaluate(bars(5, 3, 4, 2)).active
    assert not low.evaluate(bars(9, 1, 4, 2)).active  # 1 was lower, within the window
    assert low.evaluate(bars(1, 9, 4, 3, 2)).active  # the 1 has dropped out of the 4-bar window
    assert high.evaluate(bars(1, 2, 3)) is None  # not enough history


def test_new_high_defaults_to_20_bars():
    assert Rule.from_dict({"kind": "new_high"}).bars == 20
    assert Rule.from_dict({"kind": "new_high"}).describe() == "highest close in 20 bars"


def test_parse_duration():
    assert parse_duration("30m") == 1800
    assert parse_duration(" 6H ") == 21600
    assert parse_duration("2d") == 172800


def test_cooldown_holds_back_level_alerts():
    rule = Rule.from_dict({"kind": "price_above", "value": 100, "cooldown": "1h"})
    assert rule.cooldown == 3600
    state, fired = None, []
    # (close, seconds) - crosses above at 0s, dips, back above at 600s (too soon), and at 4000s.
    for close, now in ((101, 0), (99, 300), (102, 600), (99, 3000), (103, 4000)):
        fire, state = decide(rule, rule.evaluate(bars(close)), state, now)
        fired.append(fire)
    assert fired == [True, False, False, False, True]
    assert state["last_fired"] == 4000


def test_cooldown_holds_back_event_alerts():
    rule = Rule.from_dict({"kind": "new_high", "bars": 2, "cooldown": "1d"})
    fire1, state = decide(rule, rule.evaluate(bars(1, 2)), None, now=0)
    fire2, state = decide(rule, rule.evaluate(bars(1, 2, 3)), state, now=3600)  # new bar, new high, too soon
    fire3, state = decide(rule, rule.evaluate(bars(1, 2, 3, 4)), state, now=90000)
    assert (fire1, fire2, fire3) == (True, False, True)


def test_without_cooldown_last_fired_is_still_recorded():
    rule = Rule.from_dict({"kind": "price_above", "value": 1})
    fire, state = decide(rule, rule.evaluate(bars(2)), None, now=123)
    assert fire and state == {"active": True, "last_fired": 123}


def test_messages_keep_full_prices():
    # Regression test for #26: messages used to round to 6 significant digits.
    ev = Rule.from_dict({"kind": "price_above", "value": 100000.5}).evaluate(bars(101234.56))
    assert ev.message == "price 101,234.56 is price above 100,000.50"
    cross = Rule.from_dict({"kind": "cross_above", "over": "sma:2"}).evaluate(bars(100000, 99000, 123456.78))
    assert cross.message.endswith("(123,456.78 vs 111,228.39)")


def test_rule_id_includes_source_and_interval():
    # Regression test for #24.
    rule = Rule.from_dict({"kind": "price_above", "value": 1})
    keys = {
        rule_id("BTCUSDT", rule, "binance", "1d"),
        rule_id("BTCUSDT", rule, "binance", "4h"),
        rule_id("BTCUSDT", rule, "stooq", "1d"),
    }
    assert len(keys) == 3
    assert legacy_rule_id("BTCUSDT", rule) not in keys
