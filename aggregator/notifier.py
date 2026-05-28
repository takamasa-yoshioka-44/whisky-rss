"""Discord / Slack への Webhook 通知。"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Iterable

import requests

log = logging.getLogger(__name__)

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
NOTIFY_BODY_MAX_CHARS = int(os.environ.get("NOTIFY_BODY_MAX_CHARS", "400"))


@dataclass
class NotifyPayload:
    feed_name: str
    title: str
    link: str
    summary: str
    matched_rule: str


def _truncate(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _post(url: str, json_body: dict, label: str) -> bool:
    try:
        resp = requests.post(url, json=json_body, timeout=15)
        if resp.status_code >= 300:
            log.warning(
                "[%s] notify failed: status=%s body=%s",
                label,
                resp.status_code,
                resp.text[:200],
            )
            return False
        return True
    except requests.RequestException as e:
        log.warning("[%s] notify exception: %s", label, e)
        return False


def send_discord(payload: NotifyPayload) -> bool:
    if not DISCORD_WEBHOOK_URL:
        return False
    body = _truncate(payload.summary, NOTIFY_BODY_MAX_CHARS)
    embed = {
        "title": _truncate(payload.title, 240),
        "url": payload.link,
        "description": body,
        "footer": {"text": f"{payload.feed_name} · rule: {payload.matched_rule}"},
    }
    return _post(
        DISCORD_WEBHOOK_URL,
        {"embeds": [embed]},
        label="discord",
    )


def send_slack(payload: NotifyPayload) -> bool:
    if not SLACK_WEBHOOK_URL:
        return False
    body = _truncate(payload.summary, NOTIFY_BODY_MAX_CHARS)
    text = (
        f"*<{payload.link}|{payload.title}>*\n"
        f"{body}\n"
        f"_{payload.feed_name} · rule: {payload.matched_rule}_"
    )
    return _post(SLACK_WEBHOOK_URL, {"text": text}, label="slack")


def notify(payload: NotifyPayload, channels: Iterable[str]) -> None:
    channels = set(channels or [])
    if "discord" in channels:
        send_discord(payload)
    if "slack" in channels:
        send_slack(payload)
