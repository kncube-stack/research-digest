from __future__ import annotations

import argparse
import json
import sys

from research_digest import DigestPipeline, DigestStore, load_config
from research_digest.server import run_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Research Digest web app")
    parser.add_argument("--config", default="config.json", help="Path to config JSON (default: config.json)")
    parser.add_argument("--db", default="digest.db", help="SQLite database path")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", default=8000, type=int, help="Bind port")
    parser.add_argument("--refresh-on-start", action="store_true", help="Force regenerate digest before serving")
    parser.add_argument("--once-json", action="store_true", help="Generate digest once and print strict JSON")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    config = load_config(args.config)
    store = DigestStore(args.db)
    pipeline = DigestPipeline(config=config, store=store)

    try:
        if args.once_json:
            posts = pipeline.ensure_weekly_digest(force=args.refresh_on_start)
            print(json.dumps(posts, ensure_ascii=False, indent=2))
            return 0

        # Warm up so the first page load already has papers when possible.
        pipeline.ensure_weekly_digest(force=args.refresh_on_start)
    except Exception as exc:
        print(f"Warm-up generation failed: {exc}", file=sys.stderr)

    run_server(config=config, store=store, pipeline=pipeline, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
