from __future__ import annotations

import re
from dataclasses import asdict
from datetime import date
from typing import Dict, List, Sequence, Set, Tuple

from .config import AppConfig
from .models import CandidatePaper, RankedPaper


STUDY_PATTERNS = [
    ("systematic review", [r"systematic review", r"review and meta", r"meta-analysis"]),
    ("meta-analysis", [r"meta-analysis", r"meta analysis"]),
    (
        "randomized controlled trial",
        [r"randomized", r"randomised", r"double-blind", r"placebo-controlled", r"trial"],
    ),
    ("mendelian randomization", [r"mendelian randomization", r"mendelian randomisation"]),
    ("cohort", [r"cohort", r"longitudinal", r"prospective"]),
    ("case-control", [r"case-control", r"case control"]),
    ("cross-sectional", [r"cross-sectional", r"cross sectional"]),
    ("animal", [r"mice", r"mouse", r"rat", r"animal model", r"murine"]),
    ("mechanistic", [r"in vitro", r"mechanism", r"pathway", r"cell line"]),
    ("theory", [r"theory", r"conceptual", r"commentary"]),
]

STUDY_PRIORITY = {
    "systematic review": 4.0,
    "meta-analysis": 4.0,
    "randomized controlled trial": 3.4,
    "mendelian randomization": 3.0,
    "cohort": 2.7,
    "case-control": 2.3,
    "cross-sectional": 2.0,
    "animal": 1.7,
    "mechanistic": 1.6,
    "theory": 1.2,
    "unknown": 1.8,
}

TIER1_HINTS = [
    "nature",
    "science",
    "cell",
    "lancet",
    "new england journal of medicine",
    "jama",
    "bmj",
    "proceedings of the national academy of sciences",
    "pnas",
]


def infer_study_type(paper: CandidatePaper) -> str:
    text = f"{paper.title} {paper.abstract}".lower()
    for label, patterns in STUDY_PATTERNS:
        if any(re.search(pattern, text) for pattern in patterns):
            return label
    return "unknown"


def classify_journal_tier(journal: str, config: AppConfig) -> int:
    text = (journal or "").lower()

    if any(h in text for h in TIER1_HINTS):
        return 1

    for value in config.JOURNAL_PRIORITIES.get("tier1", []):
        if value.lower() in text:
            return 1

    for value in config.JOURNAL_PRIORITIES.get("tier2", []):
        if value.lower() in text:
            return 2

    for value in config.JOURNAL_PRIORITIES.get("tier3", []):
        if value.lower() in text:
            return 3

    return 3


def match_topics(paper: CandidatePaper, config: AppConfig) -> Dict[str, float]:
    text = f"{paper.title} {paper.abstract}".lower()
    topic_scores: Dict[str, float] = {}
    for topic in config.TOPICS:
        key = topic.lower()
        keywords = config.TOPIC_KEYWORDS.get(key) or [key]
        score = 0.0
        for kw in keywords:
            kw = kw.strip().lower()
            if not kw:
                continue
            if kw in text:
                # Full topic phrase gets stronger weighting than token-level hits.
                score += 2.5 if kw == key else 1.0
        if topic.lower() in text:
            score += 1.5
        if score > 0:
            topic_scores[topic] = score
    return topic_scores


def score_candidate(paper: CandidatePaper, config: AppConfig, now: date) -> Tuple[float, Dict[str, float]]:
    paper.study_type = infer_study_type(paper)
    journal_tier = classify_journal_tier(paper.journal, config)
    topic_scores = match_topics(paper, config)

    if not topic_scores:
        return 0.0, {
            "journal": 0.0,
            "open_access": 0.0,
            "topic_match": 0.0,
            "study_type": 0.0,
            "novelty": 0.0,
        }

    journal_component = {1: 40.0, 2: 26.0, 3: 14.0}[journal_tier]

    if paper.open_access_status == "OPEN_ACCESS":
        oa_component = 18.0 if config.OPEN_ACCESS_PRIORITY else 10.0
    elif paper.open_access_status == "PAYWALLED":
        oa_component = -3.0 if config.OPEN_ACCESS_PRIORITY else 0.0
    else:
        oa_component = 4.0

    top_topic_score = max(topic_scores.values())
    if top_topic_score >= 4:
        topic_component = 28.0
    elif top_topic_score >= 2.2:
        topic_component = 19.0
    else:
        topic_component = 10.0

    study_component = STUDY_PRIORITY.get(paper.study_type, STUDY_PRIORITY["unknown"]) * 4.3

    age_days = (now - paper.publication_date).days
    if age_days <= 1:
        novelty_component = 8.0
    elif age_days <= 3:
        novelty_component = 6.0
    else:
        novelty_component = 4.0

    total = journal_component + oa_component + topic_component + study_component + novelty_component

    breakdown = {
        "journal": journal_component,
        "open_access": oa_component,
        "topic_match": topic_component,
        "study_type": study_component,
        "novelty": novelty_component,
    }
    return total, breakdown


def select_papers(
    candidates: Sequence[CandidatePaper],
    config: AppConfig,
    seen_doi: Set[str],
    seen_titles: Set[str],
    now: date,
) -> List[RankedPaper]:
    ranked: List[RankedPaper] = []

    for paper in candidates:
        if paper.doi and paper.doi.lower() in seen_doi:
            continue
        if (not paper.doi) and paper.title.lower().strip() in seen_titles:
            continue
        if not paper.peer_reviewed:
            continue

        score, breakdown = score_candidate(paper, config, now)
        if score <= 0:
            continue

        matched_topics = match_topics(paper, config)
        paper.topic_tags = sorted(matched_topics.keys(), key=lambda t: matched_topics[t], reverse=True)
        paper.score = score
        ranked.append(RankedPaper(paper=paper, score_breakdown=breakdown))

    ranked.sort(key=lambda x: x.paper.score, reverse=True)

    selected: List[RankedPaper] = []
    selected_keys: Set[str] = set()

    def _try_add(candidate: RankedPaper) -> bool:
        key = candidate.paper.dedupe_key()
        if key in selected_keys:
            return False
        if len(selected) >= config.MAX_PAPERS_PER_WEEK:
            return False
        selected_keys.add(key)
        selected.append(candidate)
        return True

    # First pass: enforce minimum per topic when available.
    for topic in config.TOPICS:
        topic_matches = [c for c in ranked if topic in c.paper.topic_tags and c.paper.dedupe_key() not in selected_keys]
        for candidate in topic_matches[: config.MIN_PAPERS_PER_TOPIC]:
            if not _try_add(candidate):
                break

    # Second pass: fill remaining by total score.
    for candidate in ranked:
        if len(selected) >= config.MAX_PAPERS_PER_WEEK:
            break
        _try_add(candidate)

    selected.sort(key=lambda x: x.paper.score, reverse=True)
    return selected


def debug_rankings(selected: Sequence[RankedPaper]) -> List[Dict[str, object]]:
    payload: List[Dict[str, object]] = []
    for ranked in selected:
        item = asdict(ranked.paper)
        item["score_breakdown"] = ranked.score_breakdown
        payload.append(item)
    return payload
