import pytest

from signalwatch.notify import NotifyError, build_notifiers, load_dotenv


def test_console_notifier():
    printed = []
    [n] = build_notifiers(["console"], env={}, echo=printed.append)
    n.send("BTCUSDT: hello")
    assert printed == ["ALERT  BTCUSDT: hello"]


def test_discord_and_telegram_post_the_right_payloads():
    posts = []
    env = {
        "SIGNALWATCH_DISCORD_WEBHOOK": "https://discord.com/api/webhooks/1/abc",
        "SIGNALWATCH_TELEGRAM_TOKEN": "123:XYZ",
        "SIGNALWATCH_TELEGRAM_CHAT_ID": "42",
    }
    notifiers = build_notifiers(["discord", "telegram"], env=env, post=lambda url, body: posts.append((url, body)))
    for n in notifiers:
        n.send("x" * 5000)
    assert posts[0] == ("https://discord.com/api/webhooks/1/abc", {"content": "x" * 2000})
    assert posts[1] == ("https://api.telegram.org/bot123:XYZ/sendMessage", {"chat_id": "42", "text": "x" * 4096})


@pytest.mark.parametrize(
    "channels, env, message",
    [
        (["discord"], {}, "SIGNALWATCH_DISCORD_WEBHOOK"),
        (["discord"], {"SIGNALWATCH_DISCORD_WEBHOOK": "http://insecure"}, "SIGNALWATCH_DISCORD_WEBHOOK"),
        (["telegram"], {"SIGNALWATCH_TELEGRAM_TOKEN": "t"}, "SIGNALWATCH_TELEGRAM_CHAT_ID"),
        (["pager"], {}, "unknown notify channel"),
    ],
)
def test_missing_settings_are_named(channels, env, message):
    with pytest.raises(NotifyError, match=message):
        build_notifiers(channels, env=env)


def test_load_dotenv(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "# comment\n"
        "SIGNALWATCH_DISCORD_WEBHOOK=https://example.test/hook\n"
        'export SIGNALWATCH_TELEGRAM_TOKEN="abc:123"\n'
        "SIGNALWATCH_TELEGRAM_CHAT_ID=\n"
        "ALREADY=from-file\n"
        "not a setting\n"
    )
    env = {"ALREADY": "from-shell"}
    assert load_dotenv(str(path), env) == 2
    assert env == {
        "ALREADY": "from-shell",
        "SIGNALWATCH_DISCORD_WEBHOOK": "https://example.test/hook",
        "SIGNALWATCH_TELEGRAM_TOKEN": "abc:123",
    }
    assert load_dotenv(str(tmp_path / "missing.env"), env) == 0
