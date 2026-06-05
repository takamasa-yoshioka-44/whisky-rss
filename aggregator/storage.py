"""SQLite を使った既読/重複管理。"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DB_PATH = Path(os.environ.get("WHISKY_DB_PATH", "/app/data/whisky.sqlite"))


def _ensure_dir() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def init_db() -> None:
    _ensure_dir()
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_entries (
                id TEXT PRIMARY KEY,
                feed_id TEXT NOT NULL,
                title TEXT,
                link TEXT,
                published TEXT,
                first_seen_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        # 後付けカラム(既存DB互換のため ALTER で追加)
        for col, ddl in [
            ("matched_rule", "ALTER TABLE seen_entries ADD COLUMN matched_rule TEXT"),
            ("summary", "ALTER TABLE seen_entries ADD COLUMN summary TEXT"),
            ("notified_at", "ALTER TABLE seen_entries ADD COLUMN notified_at TEXT"),
        ]:
            if not _has_column(conn, "seen_entries", col):
                conn.execute(ddl)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_seen_feed ON seen_entries(feed_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_seen_rule ON seen_entries(matched_rule)"
        )
        conn.commit()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def make_entry_id(feed_id: str, entry_link: str | None, entry_id: str | None) -> str:
    """フィードごとに一意なIDを生成。link/idがなければタイトル＋日付などで補う想定。"""
    seed = f"{feed_id}::{entry_id or ''}::{entry_link or ''}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()


def is_seen(entry_id: str) -> bool:
    with connect() as conn:
        cur = conn.execute("SELECT 1 FROM seen_entries WHERE id = ?", (entry_id,))
        return cur.fetchone() is not None


def mark_seen(
    entry_id: str,
    feed_id: str,
    title: str | None,
    link: str | None,
    published: str | None,
    matched_rule: str | None = None,
    summary: str | None = None,
    notified: bool = False,
) -> None:
    """INSERT OR IGNORE で既読登録。

    matched_rule: ルールにマッチしたか(分類・出力RSS用)。
    notified: 実際に通知配信が成功したか。成功時のみ notified_at を打つ。
    """
    notified_at = "datetime('now')" if notified else "NULL"
    with connect() as conn:
        conn.execute(
            f"""
            INSERT OR IGNORE INTO seen_entries
                (id, feed_id, title, link, published, matched_rule, summary, notified_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, {notified_at})
            """,
            (entry_id, feed_id, title, link, published, matched_rule, summary),
        )
        conn.commit()


# --------------------- RSS 出力用クエリ ---------------------

def recent_notified(
    rule: str | None = None, days: int = 30, limit: int = 200
) -> list[dict]:
    """通知対象になった記事を新しい順で返す。rule=None なら全 rule 横断。"""
    where = [
        "matched_rule IS NOT NULL",
        "COALESCE(notified_at, first_seen_at) >= datetime('now', ?)",
    ]
    params: list[object] = [f"-{int(days)} days"]
    if rule:
        where.append("matched_rule = ?")
        params.append(rule)
    sql = f"""
        SELECT id, feed_id, title, link, published, summary,
               matched_rule, notified_at
        FROM seen_entries
        WHERE {' AND '.join(where)}
        ORDER BY COALESCE(notified_at, first_seen_at) DESC, first_seen_at DESC
        LIMIT ?
    """
    params.append(int(limit))
    with connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def distinct_rules() -> list[str]:
    with connect() as conn:
        cur = conn.execute(
            "SELECT DISTINCT matched_rule FROM seen_entries "
            "WHERE matched_rule IS NOT NULL"
        )
        return [r[0] for r in cur.fetchall() if r[0]]
