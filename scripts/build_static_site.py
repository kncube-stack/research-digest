#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research_digest import DigestPipeline, DigestStore, load_config
from research_digest.server import _render_home, _render_post
from research_digest.store import slugify


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _copy_static_assets(out_dir: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    css_src = project_root / "research_digest" / "static" / "styles.css"
    css_dst = out_dir / "static" / "styles.css"
    css_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(css_src, css_dst)


def _ensure_post_slugs(posts: List[Dict[str, object]]) -> List[Dict[str, object]]:
    used = set()
    out: List[Dict[str, object]] = []

    for idx, post in enumerate(posts):
        payload = dict(post)
        base = str(payload.get("slug") or slugify(str(payload.get("title") or payload.get("paper_title") or f"post-{idx+1}")))
        slug = base
        suffix = 2
        while slug in used:
            slug = f"{base}-{suffix}"
            suffix += 1
        used.add(slug)
        payload["slug"] = slug
        out.append(payload)

    return out


def build_site(config_path: str, db_path: str, out_dir: str, refresh: bool) -> None:
    config = load_config(config_path)
    store = DigestStore(db_path)
    pipeline = DigestPipeline(config=config, store=store)

    posts = pipeline.ensure_weekly_digest(force=refresh)
    posts = _ensure_post_slugs(posts)

    week_key = pipeline.week_key()
    target = Path(out_dir)

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    _copy_static_assets(target)

    # Root pages
    _write_text(target / "index.html", _render_home(posts, week_key))
    digest_json = json.dumps(posts, ensure_ascii=False, indent=2)
    _write_text(target / "digest.json", digest_json)
    # Alias so static hosts can also serve /api/digest without rewrites.
    _write_text(target / "api" / "digest", digest_json)
    _write_text(target / "404.html", _render_home(posts, week_key))
    _write_text(target / ".nojekyll", "")

    # Post pages for pretty URLs: /post/<slug>/
    for post in posts:
        slug = str(post.get("slug") or "post")
        _write_text(target / "post" / slug / "index.html", _render_post(post))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build static Research Digest site for Netlify")
    parser.add_argument("--config", default="config.json", help="Config JSON path")
    parser.add_argument("--db", default="digest.db", help="SQLite DB path")
    parser.add_argument("--out", default="site", help="Output directory")
    parser.add_argument("--refresh", action="store_true", help="Force digest refresh before rendering")
    args = parser.parse_args()

    build_site(config_path=args.config, db_path=args.db, out_dir=args.out, refresh=args.refresh)
