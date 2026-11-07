"""Where alerts go: the terminal, a Discord channel, or a Telegram chat.

Webhook URLs and bot tokens are read from environment variables (or a local
.env file), never from the watchlist, so the watchlist can be shared or committed
safely.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from .providers import TIMEOUT, USER_AGENT

DISCORD_ENV = "SIGNALWATCH_DISCORD_WEBHOOK"
TELEGRAM_TOKEN_ENV = "SIGNALWATCH_TELEGRAM_TOKEN"
TELEGRAM_CHAT_ENV = "SIGNALWATCH_TELEGRAM_CHAT_ID"
CHANNELS = ("console", "discord", "telegram")


class NotifyError(Exception):
    pass


Poster = Callable[[str, dict[str, object]], None]


def post_json(url: str, payload: dict[str, object]) -> None:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT):
            pass
    except urllib.error.HTTPError as exc:
        # Never include the URL: for webhooks and bots it contains the secret.
        raise NotifyError(f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:200]}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise NotifyError(f"could not connect: {getattr(exc, 'reason', exc)}") from None


@dataclass
class Notifier:
    name: str
    send: Callable[[str], None]


def build_notifiers(
    channels: list[str],
    env: Mapping[str, str] | None = None,
    post: Poster = post_json,
    echo: Callable[[str], None] = print,
) -> list[Notifier]:
    """Sets up the requested channels, explaining exactly which setting is missing if any."""
    env = os.environ if env is None else env
    notifiers = []
    for channel in channels:
        if channel == "console":
            notifiers.append(Notifier("console", lambda text: echo(f"ALERT  {text}")))
        elif channel == "discord":
            url = env.get(DISCORD_ENV, "").strip()
            if not url.startswith("https://"):
                raise NotifyError(f"discord: set {DISCORD_ENV} to your channel's webhook URL")
            notifiers.append(Notifier("discord", lambda text, url=url: post(url, {"content": text[:2000]})))
        elif channel == "telegram":
            token = env.get(TELEGRAM_TOKEN_ENV, "").strip()
            chat = env.get(TELEGRAM_CHAT_ENV, "").strip()
            if not token or not chat:
                raise NotifyError(f"telegram: set {TELEGRAM_TOKEN_ENV} and {TELEGRAM_CHAT_ENV}")
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            notifiers.append(
                Notifier("telegram", lambda text, url=url, chat=chat: post(url, {"chat_id": chat, "text": text[:4096]}))
            )
        else:
            raise NotifyError(f"unknown notify channel {channel!r}; choose from {', '.join(CHANNELS)}")
    return notifiers


def load_dotenv(path: str = ".env", env: dict[str, str] | None = None) -> int:
    """Reads KEY=value lines from a .env file into ``env`` (default: os.environ).

    Variables that are already set win. Returns how many were added. A missing file is fine.
    """
    target = os.environ if env is None else env
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except FileNotFoundError:
        return 0
    added = 0
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if key and value and key not in target:
            target[key] = value
            added += 1
    return added
