import pytest

from signalwatch.config import EXAMPLE, ConfigError, load_config, parse_config


def test_example_watchlist_is_valid():
    config = parse_config(EXAMPLE)
    assert [w.symbol for w in config.watches] == ["BTCUSDT", "ETHUSDT", "spy.us"]
    assert config.watches[1].interval == "4h"  # per-symbol override
    assert config.watches[0].interval == "1d"  # from [settings]
    assert config.notify == ["console"]
    assert config.history == 300
    assert config.watches[0].rules[0].note == "oversold"


def test_minimal_watchlist_uses_defaults():
    config = parse_config('[[watch]]\nsymbol = "BTCUSDT"\n[[watch.rule]]\nkind = "price_above"\nvalue = 1\n')
    assert config.watches[0].source == "binance"
    assert config.watches[0].interval == "1d"


def test_notify_accepts_a_single_string_and_drops_duplicates():
    text = '[settings]\nnotify = "discord"\n[[watch]]\nsymbol = "X"\n[[watch.rule]]\nkind = "price_above"\nvalue = 1\n'
    assert parse_config(text).notify == ["discord"]
    text = text.replace('"discord"', '["console", "console"]')
    assert parse_config(text).notify == ["console"]


RULE = '[[watch.rule]]\nkind = "price_above"\nvalue = 1\n'


@pytest.mark.parametrize(
    "text, message",
    [
        ("not = [valid", "not valid TOML"),
        ("", "at least one"),
        ("[setings]\n", "unknown section"),
        ("[settings]\nhistory = 1\n" + '[[watch]]\nsymbol="X"\n' + RULE, "history"),
        ('[settings]\nnotify = ["email"]\n[[watch]]\nsymbol="X"\n' + RULE, "unknown notify channel"),
        ("[settings]\ncolour = 1\n", "unknown setting"),
        ("[[watch]]\n" + RULE, "needs a symbol"),
        ('[[watch]]\nsymbol = "X"\n', "at least one \\[\\[watch.rule\\]\\]"),
        ('[[watch]]\nsymbol = "X"\nsource = "kraken"\n' + RULE, "source must be"),
        ('[[watch]]\nsymbol = "aapl.us"\nsource = "stooq"\ninterval = "1h"\n' + RULE, "doesn't offer"),
        ('[[watch]]\nsymbol = "X"\n[[watch.rule]]\nkind = "rsi_above"\nvalue = 300\n', "X, rule #1"),
        ('[[watch]]\nsymbol = "X"\nsymbl = "Y"\n' + RULE, "unknown setting"),
    ],
)
def test_bad_watchlists_are_explained(text, message):
    with pytest.raises(ConfigError, match=message):
        parse_config(text)


def test_load_config_missing_file_suggests_init(tmp_path):
    with pytest.raises(ConfigError, match="signalwatch init"):
        load_config(tmp_path / "nope.toml")


def test_examples_file_matches_init_output():
    from pathlib import Path

    example_file = Path(__file__).parent.parent / "examples" / "watchlist.toml"
    assert example_file.read_text(encoding="utf-8") == EXAMPLE
