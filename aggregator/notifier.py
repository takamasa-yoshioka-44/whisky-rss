"""Discord / Slack への Webhook 通知。"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Iterable

import requests

from translator import maybe_translate

log = logging.getLogger(__name__)

# Discord embed の description 上限(API 仕様は 4096 字)
DISCORD_DESC_MAX_CHARS = 4096

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
        log.warning(
            "[discord] webhook URL not set; skipping notification for %r",
            payload.title[:80],
        )
        return False
    # 英語記事ならタイトル・本文を翻訳して併記する。
    # 翻訳が走らない(日本語記事 / キー未設定 / 失敗)場合は従来どおりの出力になる。
    t_title, title_translated = maybe_translate(payload.title)
    t_body, body_translated = maybe_translate(payload.summary)

    orig_body = _truncate(payload.summary, NOTIFY_BODY_MAX_CHARS)

    if title_translated or body_translated:
        # 訳文を主に、原文を末尾に併記
        main_body = _truncate(t_body, NOTIFY_BODY_MAX_CHARS) if body_translated else orig_body
        orig_lines = []
        if title_translated:
            orig_lines.append(_truncate(payload.title, 240))
        orig_lines.append(orig_body)
        description = _truncate(
            main_body + "\n\n—— 原文 / Original ——\n" + "\n".join(orig_lines),
            DISCORD_DESC_MAX_CHARS,
        )
        title = _truncate(t_title if title_translated else payload.title, 240)
    else:
        description = orig_body
        title = _truncate(payload.title, 240)

    embed = {
        "title": title,
        "url": payload.link,
        "description": description,
        "footer": {"text": f"{payload.feed_name} · rule: {payload.matched_rule}"},
    }
    return _post(
        DISCORD_WEBHOOK_URL,
        {"embeds": [embed]},
        label="discord",
    )


def send_slack(payload: NotifyPayload) -> bool:
    if not SLACK_WEBHOOK_URL:
        log.warning(
            "[slack] webhook URL not set; skipping notification for %r",
            payload.title[:80],
        )
        return False
    body = _truncate(payload.summary, NOTIFY_BODY_MAX_CHARS)
    text = (
        f"*<{payload.link}|{payload.title}>*\n"
        f"{body}\n"
        f"_{payload.feed_name} · rule: {payload.matched_rule}_"
    )
    return _post(SLACK_WEBHOOK_URL, {"text": text}, label="slack")


def notify(payload: NotifyPayload, channels: Iterable[str]) -> bool:
    """指定チャンネルへ通知。実際に1つでも配信成功したら True を返す。"""
    channels = set(channels or [])
    sent = False
    if "discord" in channels:
        sent = send_discord(payload) or sent
    if "slack" in channels:
        sent = send_slack(payload) or sent
    return sent
