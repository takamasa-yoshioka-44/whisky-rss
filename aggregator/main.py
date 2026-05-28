"""whisky-rss aggregator のメインエントリ。

- config/feeds.yaml の購読フィードを取得
- 既読/重複を SQLite で除外
- config/keywords.yaml のルールでフィルタ
- Discord / Slack へ通知
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import feedparser
import yaml

from notifier import NotifyPayload, notify
from rss_writer import write_feed, write_index_html
from storage import (
    distinct_rules,
    init_db,
    is_seen,
    make_entry_id,
    mark_seen,
    recent_notified,
)

CONFIG_DIR = Path(os.environ.get("WHISKY_CONFIG_DIR", "/app/config"))
RSSHUB_BASE_URL = os.environ.get("RSSHUB_BASE_URL", "http://rsshub:1200").rstrip("/")

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("whisky-rss")


# ----------------------------- config -----------------------------

@dataclass
class Feed:
    id: str
    name: str
    url: str
    category: str
    region: str
    enabled: bool
    notify: list[str] | None  # 任意。指定があればここに通知先を上書き


@dataclass
class Rule:
    name: str
    include: list[str]
    exclude: list[str]
    channels: list[str]


def _expand_vars(value: str) -> str:
    # ${RSSHUB} を RSSHUB_BASE_URL に置換
    return value.replace("${RSSHUB}", RSSHUB_BASE_URL)


def load_feeds() -> list[Feed]:
    path = CONFIG_DIR / "feeds.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    feeds: list[Feed] = []
    for raw in data.get("feeds", []):
        feeds.append(
            Feed(
                id=raw["id"],
                name=raw.get("name", raw["id"]),
                url=_expand_vars(raw["url"]),
                category=raw.get("category", "news"),
                region=raw.get("region", "global"),
                enabled=bool(raw.get("enabled", True)),
                notify=raw.get("notify"),
            )
        )
    return feeds


def load_rules() -> list[Rule]:
    path = CONFIG_DIR / "keywords.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules: list[Rule] = []
    for raw in data.get("rules", []):
        rules.append(
            Rule(
                name=raw["name"],
                include=[s for s in raw.get("include", []) if s],
                exclude=[s for s in raw.get("exclude", []) if s],
                channels=list(raw.get("channels", []) or []),
            )
        )
    return rules


# ----------------------------- matching -----------------------------

def _haystack(entry: Any) -> str:
    parts = [
        entry.get("title") or "",
        entry.get("summary") or "",
        entry.get("description") or "",
    ]
    return " ".join(parts).lower()


def _contains_any(text: str, needles: list[str]) -> str | None:
    for n in needles:
        if not n:
            continue
        if n.lower() in text:
            return n
    return None


def match_rule(entry: Any, rules: list[Rule]) -> Rule | None:
    text = _haystack(entry)
    for rule in rules:
        if rule.exclude and _contains_any(text, rule.exclude):
            continue
        if not rule.include:
            continue
        if _contains_any(text, rule.include):
            return rule
    return None


# ----------------------------- main loop -----------------------------

def _summary_text(entry: Any) -> str:
    raw = entry.get("summary") or entry.get("description") or ""
    # 簡易的にHTMLタグを除去
    return re.sub(r"<[^>]+>", "", raw).strip()


def process_feed(feed: Feed, rules: list[Rule]) -> tuple[int, int]:
    """1フィードを処理。 (new_entries, notified) を返す。"""
    log.info("[%s] fetching %s", feed.id, feed.url)
    parsed = feedparser.parse(feed.url)
    if parsed.bozo and not parsed.entries:
        log.warning("[%s] parse failed: %s", feed.id, parsed.bozo_exception)
        return (0, 0)

    new_count = 0
    notify_count = 0

    for entry in parsed.entries:
        link = entry.get("link") or ""
        eid_raw = entry.get("id") or entry.get("guid") or ""
        eid = make_entry_id(feed.id, link, eid_raw)
        if is_seen(eid):
            continue

        title = (entry.get("title") or "(no title)").strip()
        published = entry.get("published") or entry.get("updated") or ""
        summary = _summary_text(entry)
        new_count += 1

        rule = match_rule(entry, rules)
        matched_rule: str | None = None
        if rule and rule.channels:
            channels = feed.notify or rule.channels
            payload = NotifyPayload(
                feed_name=feed.name,
                title=title,
                link=link,
                summary=summary,
                matched_rule=rule.name,
            )
            notify(payload, channels)
            notify_count += 1
            matched_rule = rule.name
            log.info(
                "[%s] notify: rule=%s title=%r",
                feed.id,
                rule.name,
                title[:80],
            )
        else:
            log.debug("[%s] skip (no rule match): %r", feed.id, title[:80])

        mark_seen(eid, feed.id, title, link, published, matched_rule, summary)

    log.info("[%s] new=%d notified=%d", feed.id, new_count, notify_count)
    return (new_count, notify_count)


def main() -> int:
    init_db()
    feeds = [f for f in load_feeds() if f.enabled]
    rules = load_rules()
    log.info("loaded: feeds=%d rules=%d", len(feeds), len(rules))

    total_new = 0
    total_notified = 0
    for feed in feeds:
        try:
            new, notified = process_feed(feed, rules)
            total_new += new
            total_notified += notified
        except Exception as e:  # pylint: disable=broad-except
            log.exception("[%s] failed: %s", feed.id, e)

    log.info("done: total_new=%d total_notified=%d", total_new, total_notified)

    # ---- フィルタ済み RSS XML を書き出す ----
    try:
        rules_in_db = distinct_rules()
        feed_ids: list[str] = ["all"]
        write_feed(
            "all",
            "whisky-rss / all filtered",
            "全 rule にマッチした記事(直近30日)",
            recent_notified(rule=None, days=30, limit=300),
        )
        for r in sorted(rules_in_db):
            write_feed(
                r,
                f"whisky-rss / {r}",
                f"rule={r} にマッチした記事(直近30日)",
                recent_notified(rule=r, days=30, limit=300),
            )
            feed_ids.append(r)
        write_index_html(feed_ids)
        log.info("rss output: %d feeds", len(feed_ids))
    except Exception as e:  # pylint: disable=broad-except
        log.exception("rss output failed: %s", e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
