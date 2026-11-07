import argparse

import pytest

from signalwatch import cli, providers
from signalwatch.cli import main, parse_every

CSV = "Date,Open,High,Low,Close,Volume\n" + "".join(f"2026-10-{i:02d},1,1,1,{100 + i},1\n" for i in range(1, 31))
WATCHLIST = '[[watch]]\nsymbol = "spy.us"\nsource = "stooq"\n[[watch.rule]]\nkind = "price_above"\nvalue = 120\n'


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(providers, "http_get", lambda url: CSV)


def test_init_writes_an_example_and_refuses_to_overwrite(tmp_path, capsys):
    path = tmp_path / "w.toml"
    assert main(["init", "-c", str(path)]) == 0
    assert "[[watch]]" in path.read_text()
    assert main(["init", "-c", str(path)]) == 1
    assert main(["init", "-c", str(path), "--force"]) == 0


def test_check_alerts_then_remembers(tmp_path, capsys, offline):
    config = tmp_path / "w.toml"
    config.write_text(WATCHLIST)
    state = tmp_path / "state.json"
    assert main(["check", "-c", str(config), "--state", str(state)]) == 0
    out = capsys.readouterr().out
    assert "ALERT  spy.us: price 130.00 is price above 120.00" in out
    assert "checked 1 of 1 symbol(s), 1 alert(s)" in out
    assert main(["check", "-c", str(config), "--state", str(state)]) == 0
    assert "0 alert(s)" in capsys.readouterr().out


def test_check_dry_run(tmp_path, capsys, offline):
    config = tmp_path / "w.toml"
    config.write_text(WATCHLIST)
    state = tmp_path / "state.json"
    assert main(["check", "-c", str(config), "--state", str(state), "--dry-run"]) == 0
    assert "WOULD ALERT  spy.us" in capsys.readouterr().out
    assert not state.exists()


def test_check_reports_config_errors_with_exit_code_2(tmp_path, capsys):
    assert main(["check", "-c", str(tmp_path / "missing.toml")]) == 2
    assert "signalwatch init" in capsys.readouterr().err


def test_check_exit_code_1_when_nothing_could_be_fetched(tmp_path, capsys, monkeypatch):
    def offline(url):
        raise providers.ProviderError("could not reach stooq.com: offline")

    monkeypatch.setattr(providers, "http_get", offline)
    config = tmp_path / "w.toml"
    config.write_text(WATCHLIST)
    assert main(["check", "-c", str(config), "--state", str(tmp_path / "s.json")]) == 1
    assert "offline" in capsys.readouterr().err


def test_missing_discord_webhook_is_explained(tmp_path, capsys, offline, monkeypatch):
    monkeypatch.delenv("SIGNALWATCH_DISCORD_WEBHOOK", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here
    config = tmp_path / "w.toml"
    config.write_text('[settings]\nnotify = ["discord"]\n' + WATCHLIST)
    assert main(["check", "-c", str(config)]) == 2
    assert "SIGNALWATCH_DISCORD_WEBHOOK" in capsys.readouterr().err


def test_show(capsys, offline):
    assert main(["show", "spy.us", "--source", "stooq"]) == 0
    out = capsys.readouterr().out
    assert "SPY.US (stooq, 1d bars), last close 130.00" in out
    assert "SMA 20" in out and "SMA 200  not enough history" in out
    assert "RSI 14   100.00" in out


def test_parse_every():
    assert parse_every("15m") == 900
    assert parse_every("1h") == 3600
    assert parse_every(" 90s ") == 90
    for bad in ("30s", "5", "m", "2d"):
        with pytest.raises(argparse.ArgumentTypeError):
            parse_every(bad)


def test_watch_runs_until_ctrl_c(tmp_path, capsys, offline, monkeypatch):
    config = tmp_path / "w.toml"
    config.write_text(WATCHLIST)

    def stop(seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.time, "sleep", stop)
    assert main(["watch", "-c", str(config), "--state", str(tmp_path / "s.json"), "--every", "5m"]) == 0
    out = capsys.readouterr().out
    assert "Checking every 5 minute(s)" in out and "1 alert(s)" in out and "Stopped." in out


def test_show_with_no_closed_bars_explains_instead_of_crashing(capsys, monkeypatch):
    # Regression test for #25: this used to raise IndexError.
    monkeypatch.setattr(providers, "http_get", lambda url: "[]")
    assert main(["show", "newcoin"]) == 2
    assert "no closed 1d bars for NEWCOIN yet" in capsys.readouterr().err
