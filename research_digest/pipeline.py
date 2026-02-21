from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Dict, List, Optional

from .config import AppConfig
from .fetchers import SourceFetcher
from .ranker import select_papers
from .store import DigestStore
from .writer import render_post_object


class DigestPipeline:
    def __init__(self, config: AppConfig, store: DigestStore):
        self.config = config
        self.store = store
        self.fetcher = SourceFetcher(config)

    @staticmethod
    def week_key(now: Optional[date] = None) -> str:
        today = now or date.today()
        year, week, _ = today.isocalendar()
        return f"{year}-W{week:02d}"

    def ensure_weekly_digest(self, now: Optional[date] = None, force: bool = False) -> List[Dict[str, object]]:
        week = self.week_key(now)

        if not force:
            existing = self.store.get_digest_for_week(week)
            if existing is not None:
                return existing

        posts = self.generate_digest(now=now)
        config_payload = asdict(self.config)
        self.store.save_week_digest(week, config_payload, posts)
        return posts

    def generate_digest(self, now: Optional[date] = None) -> List[Dict[str, object]]:
        today = now or date.today()

        candidates = self.fetcher.fetch_all(now=today)
        candidates = [paper for paper in candidates if self._passes_exclusions(paper)]
        seen_doi, seen_titles = self.store.get_seen_sets()

        ranked = select_papers(
            candidates=candidates,
            config=self.config,
            seen_doi=seen_doi,
            seen_titles=seen_titles,
            now=today,
        )

        posts: List[Dict[str, object]] = []
        for ranked_item in ranked:
            post = render_post_object(
                ranked_item.paper,
                summary_min_words=self.config.SUMMARY_MIN_WORDS,
                summary_max_words=self.config.SUMMARY_MAX_WORDS,
            )
            posts.append(post)

        # Strict cap guard.
        return posts[: self.config.MAX_PAPERS_PER_WEEK]

    def _passes_exclusions(self, paper) -> bool:
        excludes = {item.lower().strip() for item in self.config.EXCLUDE}
        text = f"{paper.title} {paper.journal} {paper.abstract}".lower()

        if "non-peer reviewed" in excludes and not paper.peer_reviewed:
            return False
        if "preprints only" in excludes and any(
            hint in text for hint in ("preprint", "biorxiv", "medrxiv", "arxiv", "research square")
        ):
            return False
        if "conference abstracts" in excludes and any(
            hint in text for hint in ("conference", "congress", "meeting abstract", "abstract only")
        ):
            return False
        if self.config.HUMAN_STUDIES_ONLY and paper.human_evidence != "HUMAN":
            return False
        return True
