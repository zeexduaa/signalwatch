import json

from signalwatch.config import parse_config
from signalwatch.engine import load_state, run_round, save_state
from signalwatch.notify import Notifier, NotifyError


def stooq_csv(*closes):
    lines = ["Date,Open,High,Low,Close,Volume"]
    lines += [f"2026-10-{i:02d},1,1,1,{c},1" for i, c in enumerate(closes, 1)]
    return "\n".join(lines) + "\n"


CONFIG = parse_config(
    "[settings]\nhistory = 50\n"
    '[[watch]]\nsymbol = "aaa.us"\nsource = "stooq"\n'
    '  [[watch.rule]]\n  kind = "price_above"\n  value = 100\n'
    '[[watch]]\nsymbol = "bbb.us"\nsource = "stooq"\n'
    '  [[watch.rule]]\n  kind = "price_below"\n  value = 10\n'
)


class Recorder:
    def __init__(self):
        self.sent = []

    def notifier(self, name="test"):
        return Notifier(name, self.sent.append)


def fake_market(prices):
    """prices: symbol -> list of closes. Unknown symbols fail like a bad download."""
    from signalwatch.providers import ProviderError

    def get(url):
        for symbol, closes in prices.items():
            if f"s={symbol}" in url:
                return stooq_csv(*closes)
        raise ProviderError("could not reach stooq.com: offline")

    return get


def test_alerts_once_then_stays_quiet():
    rec = Recorder()
    state = {}
    market = fake_market({"aaa.us": [99, 101], "bbb.us": [12, 11]})
    first = run_round(CONFIG, state, [rec.notifier()], get=market)
    second = run_round(CONFIG, state, [rec.notifier()], get=market)
    assert [a.symbol for a in first.alerts] == ["aaa.us"]
    assert second.alerts == []
    assert rec.sent == ["aaa.us: price 101 is price above 100. Last price 101.00 at 2026-10-02."]


def test_one_bad_symbol_does_not_stop_the_others():
    rec = Recorder()
    result = run_round(CONFIG, {}, [rec.notifier()], get=fake_market({"bbb.us": [12, 9]}))
    assert result.checked == 1
    assert "offline" in result.errors["aaa.us"]
    assert [a.symbol for a in result.alerts] == ["bbb.us"]


def test_dry_run_sends_nothing_and_remembers_nothing():
    rec = Recorder()
    state = {}
    result = run_round(CONFIG, state, [rec.notifier()], get=fake_market({"aaa.us": [101]}), dry_run=True)
    assert len(result.alerts) == 1
    assert rec.sent == [] and state == {}


def test_a_failing_notifier_is_reported_and_others_still_send():
    rec = Recorder()

    def broken(text):
        raise NotifyError("HTTP 401: bad token")

    result = run_round(
        CONFIG, {}, [Notifier("telegram", broken), rec.notifier("console")], get=fake_market({"aaa.us": [150]})
    )
    assert result.send_errors == {"telegram": "HTTP 401: bad token"}
    assert len(rec.sent) == 1


def test_state_round_trip_and_damage(tmp_path):
    path = tmp_path / "deep" / "state.json"
    save_state(path, {"k": {"active": True}})
    assert load_state(path) == {"k": {"active": True}}
    assert json.loads(path.read_text())["version"] == 1
    path.write_text("{broken")
    assert load_state(path) == {}
    assert load_state(tmp_path / "missing.json") == {}
    assert list(path.parent.glob(".state-*")) == []  # no temp files left behind
