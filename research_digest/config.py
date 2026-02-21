from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_TOPICS = [
    "nutrition",
    "evolutionary psychology",
    "relationship science",
    "personality science",
    "psychology of men and boys",
    "behaviour genetics",
    "intelligence research",
]

DEFAULT_JOURNAL_PRIORITIES = {
    "tier1": [
        "Nature",
        "Science",
        "Cell",
        "The Lancet",
        "New England Journal of Medicine",
        "JAMA",
        "BMJ",
        "PNAS",
    ],
    "tier2": [
        "Nature Medicine",
        "Nature Metabolism",
        "Nature Communications",
        "Science Advances",
        "Psychological Science",
        "Perspectives on Psychological Science",
        "Psychological Bulletin",
        "Trends in Cognitive Sciences",
        "Annual Review of Psychology",
        "Annual Review of Nutrition",
    ],
    "tier3": [],
}

DEFAULT_RSS_FEEDS = [
    {"name": "Nature", "url": "https://www.nature.com/nature.rss"},
    {"name": "Nature Communications", "url": "https://www.nature.com/ncomms.rss"},
    {"name": "PNAS", "url": "https://www.pnas.org/rss/current.xml"},
    {"name": "BMJ", "url": "https://www.bmj.com/rss/current.xml"},
    {"name": "JAMA Network Open", "url": "https://jamanetwork.com/rss/site_4/0.xml"},
    {"name": "Psychological Science", "url": "https://journals.sagepub.com/action/showFeed?type=etoc&feed=rss&jc=pssa"},
]

DEFAULT_TOPIC_KEYWORDS = {
    "nutrition": [
        "nutrition",
        "diet",
        "food",
        "intake",
        "feeding",
        "weight",
        "obesity",
        "metabolism",
    ],
    "evolutionary psychology": [
        "evolutionary psychology",
        "sexual selection",
        "mate choice",
        "adaptation",
        "evolved",
    ],
    "relationship science": [
        "relationship",
        "marriage",
        "partner",
        "attachment",
        "intimacy",
        "couple",
    ],
    "personality science": [
        "personality",
        "trait",
        "big five",
        "temperament",
        "individual differences",
    ],
    "psychology of men and boys": [
        "men",
        "boys",
        "male psychology",
        "masculinity",
        "fatherhood",
    ],
    "behaviour genetics": [
        "behaviour genetics",
        "twin",
        "heritability",
        "polygenic",
        "genome-wide",
        "mendelian randomization",
    ],
    "intelligence research": [
        "intelligence",
        "cognitive ability",
        "iq",
        "reasoning",
        "g factor",
    ],
}


@dataclass
class AppConfig:
    TIME_WINDOW_DAYS: int = 7
    TOPICS: List[str] = field(default_factory=lambda: list(DEFAULT_TOPICS))
    JOURNAL_PRIORITIES: Dict[str, List[str]] = field(
        default_factory=lambda: {
            key: list(values) for key, values in DEFAULT_JOURNAL_PRIORITIES.items()
        }
    )
    OPEN_ACCESS_PRIORITY: bool = True
    MAX_PAPERS_PER_WEEK: int = 12
    MIN_PAPERS_PER_TOPIC: int = 1
    EXCLUDE: List[str] = field(
        default_factory=lambda: ["preprints only", "conference abstracts", "non-peer reviewed"]
    )
    OUTPUT_LANGUAGE: str = "English (UK)"
    AUDIENCE_LEVEL: str = "educated non-specialist"
    USER_CAN_ADD_TOPICS: bool = True
    HUMAN_STUDIES_ONLY: bool = True
    SUMMARY_MIN_WORDS: int = 420
    SUMMARY_MAX_WORDS: int = 780

    # API-related settings
    UNPAYWALL_EMAIL: str = ""
    PUBMED_TOOL: str = "research-digest"
    PUBMED_EMAIL: str = ""

    # Source config
    RSS_FEEDS: List[Dict[str, str]] = field(default_factory=lambda: list(DEFAULT_RSS_FEEDS))
    TOPIC_KEYWORDS: Dict[str, List[str]] = field(
        default_factory=lambda: {
            topic: list(words) for topic, words in DEFAULT_TOPIC_KEYWORDS.items()
        }
    )


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _merge_with_defaults(user_cfg: Dict[str, Any]) -> Dict[str, Any]:
    cfg = AppConfig().__dict__.copy()
    for key, value in user_cfg.items():
        if key not in cfg:
            continue
        cfg[key] = value
    cfg["OPEN_ACCESS_PRIORITY"] = _coerce_bool(cfg["OPEN_ACCESS_PRIORITY"])
    cfg["HUMAN_STUDIES_ONLY"] = _coerce_bool(cfg["HUMAN_STUDIES_ONLY"])

    if not cfg["TOPICS"]:
        cfg["TOPICS"] = list(DEFAULT_TOPICS)

    # Keep keyword map extensible for user-added topics.
    topic_keywords = {
        topic.lower(): list(words)
        for topic, words in cfg.get("TOPIC_KEYWORDS", {}).items()
        if isinstance(words, list)
    }
    for topic in cfg["TOPICS"]:
        key = topic.lower()
        if key not in topic_keywords:
            topic_keywords[key] = _default_keywords_from_topic(topic)
    cfg["TOPIC_KEYWORDS"] = topic_keywords

    return cfg


def _default_keywords_from_topic(topic: str) -> List[str]:
    base = topic.lower().replace("/", " ")
    tokens = [t for t in base.split() if len(t) > 2]
    seen = set()
    out: List[str] = []
    for token in [base] + tokens:
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out


def load_config(path: str | Path = "config.json") -> AppConfig:
    config_path = Path(path)
    if config_path.exists():
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        merged = _merge_with_defaults(raw)
        return AppConfig(**merged)
    return AppConfig()
