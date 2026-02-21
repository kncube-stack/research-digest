from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple


class DigestStore:
    def __init__(self, db_path: str = "digest.db"):
        self.db_path = Path(db_path)
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS digest_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    week_key TEXT NOT NULL UNIQUE,
                    generated_at TEXT NOT NULL,
                    config_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    digest_id INTEGER NOT NULL,
                    slug TEXT NOT NULL,
                    doi TEXT,
                    title TEXT NOT NULL,
                    post_json TEXT NOT NULL,
                    FOREIGN KEY (digest_id) REFERENCES digest_runs(id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_doi (
                    doi TEXT PRIMARY KEY,
                    first_seen_week TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_titles (
                    norm_title TEXT PRIMARY KEY,
                    first_seen_week TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_digest_id ON posts(digest_id)")

    def get_seen_sets(self) -> Tuple[Set[str], Set[str]]:
        with self._conn() as conn:
            doi_rows = conn.execute("SELECT doi FROM seen_doi").fetchall()
            title_rows = conn.execute("SELECT norm_title FROM seen_titles").fetchall()
        seen_doi = {row["doi"].lower().strip() for row in doi_rows if row["doi"]}
        seen_titles = {row["norm_title"] for row in title_rows if row["norm_title"]}
        return seen_doi, seen_titles

    def get_digest_for_week(self, week_key: str) -> Optional[List[Dict[str, object]]]:
        with self._conn() as conn:
            run = conn.execute(
                "SELECT id FROM digest_runs WHERE week_key = ?", (week_key,)
            ).fetchone()
            if not run:
                return None
            rows = conn.execute(
                "SELECT post_json FROM posts WHERE digest_id = ? ORDER BY id ASC", (run["id"],)
            ).fetchall()

        posts: List[Dict[str, object]] = []
        for row in rows:
            posts.append(json.loads(row["post_json"]))
        return posts

    def get_latest_digest(self) -> Optional[List[Dict[str, object]]]:
        with self._conn() as conn:
            run = conn.execute(
                "SELECT id FROM digest_runs ORDER BY generated_at DESC LIMIT 1"
            ).fetchone()
            if not run:
                return None
            rows = conn.execute(
                "SELECT post_json FROM posts WHERE digest_id = ? ORDER BY id ASC", (run["id"],)
            ).fetchall()

        return [json.loads(row["post_json"]) for row in rows]

    def get_post_by_slug(self, slug: str) -> Optional[Dict[str, object]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT post_json FROM posts WHERE slug = ? ORDER BY id DESC LIMIT 1",
                (slug,),
            ).fetchone()
        if not row:
            return None
        return json.loads(row["post_json"])

    def save_week_digest(
        self,
        week_key: str,
        config_json: Dict[str, object],
        posts: Sequence[Dict[str, object]],
    ) -> None:
        timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        with self._conn() as conn:
            run = conn.execute(
                "SELECT id FROM digest_runs WHERE week_key = ?", (week_key,)
            ).fetchone()
            if run:
                digest_id = run["id"]
                conn.execute(
                    "UPDATE digest_runs SET generated_at = ?, config_json = ? WHERE id = ?",
                    (timestamp, json.dumps(config_json), digest_id),
                )
                conn.execute("DELETE FROM posts WHERE digest_id = ?", (digest_id,))
            else:
                cur = conn.execute(
                    "INSERT INTO digest_runs (week_key, generated_at, config_json) VALUES (?, ?, ?)",
                    (week_key, timestamp, json.dumps(config_json)),
                )
                digest_id = cur.lastrowid

            used_slugs: Set[str] = set()
            for idx, post in enumerate(posts):
                base_slug = slugify(post.get("title", f"post-{idx+1}"))
                slug = base_slug
                suffix = 2
                while slug in used_slugs:
                    slug = f"{base_slug}-{suffix}"
                    suffix += 1
                used_slugs.add(slug)

                post_payload = dict(post)
                post_payload["slug"] = slug

                doi = (post_payload.get("doi") or "").strip().lower() or None
                title = str(post_payload.get("paper_title") or post_payload.get("title") or "Untitled")

                conn.execute(
                    "INSERT INTO posts (digest_id, slug, doi, title, post_json) VALUES (?, ?, ?, ?, ?)",
                    (digest_id, slug, doi, title, json.dumps(post_payload)),
                )

                if doi:
                    conn.execute(
                        "INSERT OR IGNORE INTO seen_doi (doi, first_seen_week) VALUES (?, ?)",
                        (doi, week_key),
                    )

                norm_title = normalize_title(title)
                if norm_title:
                    conn.execute(
                        "INSERT OR IGNORE INTO seen_titles (norm_title, first_seen_week) VALUES (?, ?)",
                        (norm_title, week_key),
                    )


def slugify(value: str) -> str:
    value = value.lower().strip()
    out = []
    prev_dash = False
    for ch in value:
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        else:
            if not prev_dash:
                out.append("-")
                prev_dash = True
    slug = "".join(out).strip("-")
    return slug[:110] or "post"


def normalize_title(value: str) -> str:
    value = value.lower().strip()
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in value)
    cleaned = " ".join(cleaned.split())
    return cleaned
