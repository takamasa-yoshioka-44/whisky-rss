"""フィルタ済み RSS XML を `/app/data/out/` 配下に書き出す。

nginx サイドカー (whisky-out) がこのディレクトリを静的配信する。
Miniflux など任意の RSS クライアントから購読する想定。
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from feedgen.feed import FeedGenerator

log = logging.getLogger("whisky-rss.rss_writer")

OUT_DIR = Path(os.environ.get("WHISKY_OUT_DIR", "/app/data/out"))
# Miniflux が <link rel="self"> を見て購読URLを補正することがあるので、
# Docker network 内から見える URL を入れる。外部公開URLにしたければ env で上書き。
PUBLIC_BASE_URL = os.environ.get(
    "WHISKY_OUT_PUBLIC_URL", "http://whisky-out"
).rstrip("/")


def _parse_dt(s: str | None) -> datetime:
    """RSS の日付っぽい文字列をなるべく datetime にする。失敗したら現在時刻。"""
    if not s:
        return datetime.now(tz=timezone.utc)
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        try:
            # SQLite の datetime('now') 形式 'YYYY-MM-DD HH:MM:SS'
            return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.now(tz=timezone.utc)


def _build_feed(feed_id: str, title: str, description: str, items: list[dict]) -> FeedGenerator:
    fg = FeedGenerator()
    self_url = f"{PUBLIC_BASE_URL}/{feed_id}.xml"
    fg.id(self_url)
    fg.title(title)
    fg.link(href=self_url, rel="self")
    fg.link(href=PUBLIC_BASE_URL + "/", rel="alternate")
    fg.description(description)
    fg.language("ja")
    fg.generator("whisky-rss aggregator")
    fg.lastBuildDate(datetime.now(tz=timezone.utc))

    for it in items:
        fe = fg.add_entry()
        # 安定した guid。link が無ければ DB の id を使う
        guid = it.get("link") or f"urn:whisky-rss:{it['id']}"
        fe.id(guid)
        fe.guid(guid, permalink=bool(it.get("link")))
        fe.title(it.get("title") or "(no title)")
        if it.get("link"):
            fe.link(href=it["link"])
        # 「いつ通知されたか」を基準に並べたいので pubDate は notified_at を優先
        pub = _parse_dt(it.get("notified_at") or it.get("published"))
        fe.pubDate(pub)
        summary = it.get("summary") or ""
        rule = it.get("matched_rule") or ""
        source = it.get("feed_id") or ""
        # 本文には source / rule をフッタとして付ける(Minifluxで識別しやすい)
        body = summary
        meta = " / ".join(filter(None, [f"source: {source}", f"rule: {rule}"]))
        if meta:
            body = (body + "\n\n— " + meta) if body else meta
        fe.description(body)
        if rule:
            fe.category({"term": rule})
        if source:
            fe.category({"term": f"src:{source}"})
    return fg


def write_feed(
    feed_id: str, title: str, description: str, items: list[dict], out_dir: Path = OUT_DIR
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    fg = _build_feed(feed_id, title, description, items)
    path = out_dir / f"{feed_id}.xml"
    fg.rss_file(str(path), pretty=True)
    log.info("wrote %s (%d items)", path, len(items))
    return path


def write_index_html(feed_ids: list[str], out_dir: Path = OUT_DIR) -> Path:
    """購読URL一覧の小さな index.html。`/` を叩いたときに見えるダッシュボード代わり。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    links = "\n".join(
        f'  <li><a href="{fid}.xml">{fid}.xml</a> '
        f'<small>(<a href="{fid}.xml" target="_blank">subscribe</a>)</small></li>'
        for fid in feed_ids
    )
    html = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>whisky-rss / filtered feeds</title>
  <style>
    body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 720px;
            margin: 4rem auto; padding: 0 1rem; color: #222; }}
    h1 {{ font-size: 1.4rem; }}
    li {{ margin: 0.4rem 0; }}
    code {{ background: #f4f4f4; padding: 0 .3em; border-radius: 3px; }}
  </style>
</head>
<body>
  <h1>🥃 whisky-rss / filtered feeds</h1>
  <p>aggregator がキーワードでフィルタ済みのフィード一覧。<br>
     Miniflux などの RSS リーダーで <code>{PUBLIC_BASE_URL}/&lt;name&gt;.xml</code> を購読してください。</p>
  <ul>
{links}
  </ul>
  <hr>
  <p><small>generated at {datetime.now(tz=timezone.utc).isoformat(timespec='seconds')}</small></p>
</body>
</html>
"""
    path = out_dir / "index.html"
    path.write_text(html, encoding="utf-8")
    return path
