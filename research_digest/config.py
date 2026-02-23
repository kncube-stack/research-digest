from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_TOPICS = [
    "personality psychology",
    "intelligence cognitive abilities",
    "relationship science",
    "sex differences",
    "evolutionary psychology",
    "social psychology",
    "weight management body composition",
    "cardiometabolic outcomes",
    "dietary patterns foods",
    "diet lifestyle longitudinal",
]

DEFAULT_JOURNAL_PRIORITIES = {
    "tier1": [
        "The BMJ",
        "BMJ",
        "JAMA",
        "The Lancet",
        "New England Journal of Medicine",
        "Nature Human Behaviour",
        "Psychological Science",
        "Journal of Personality and Social Psychology",
        "Journal of Experimental Psychology: General",
        "Evolution and Human Behavior",
    ],
    "tier2": [
        "Intelligence",
        "Personality and Individual Differences",
        "Journal of Research in Personality",
        "Social Psychological and Personality Science",
        "Psychological Methods",
        "The American Journal of Clinical Nutrition",
        "The Journal of Nutrition",
        "Clinical Nutrition",
        "Circulation",
        "European Heart Journal",
        "Diabetes Care",
        "Diabetologia",
        "Obesity",
        "International Journal of Obesity",
    ],
    "tier3": [],
}

DEFAULT_RSS_FEEDS = [
    {"name": "Psychological Science", "url": "https://journals.sagepub.com/action/showFeed?type=etoc&feed=rss&jc=pssa"},
    {"name": "Nature Human Behaviour", "url": "https://www.nature.com/nathumbehav.rss"},
    {"name": "Evolution and Human Behavior", "url": "https://www.sciencedirect.com/journal/evolution-and-human-behavior/rss"},
    {"name": "Journal of Personality and Social Psychology", "url": "https://www.apa.org/pubs/journals/rss/psp-rss.xml"},
    {"name": "BMJ", "url": "https://www.bmj.com/rss/current.xml"},
    {"name": "JAMA Network Open", "url": "https://jamanetwork.com/rss/site_4/0.xml"},
    {"name": "The Lancet", "url": "https://www.thelancet.com/rssfeed/lancet_online.xml"},
    {"name": "American Journal of Clinical Nutrition", "url": "https://academic.oup.com/rss/site_6122/advanceAccess_6122.xml"},
    {"name": "Circulation", "url": "https://www.ahajournals.org/action/showFeed?type=etoc&feed=rss&jc=circ"},
    {"name": "European Heart Journal", "url": "https://academic.oup.com/rss/site_5375/advanceAccess_5375.xml"},
]

DEFAULT_TOPIC_KEYWORDS = {
    "personality psychology": [
        "big five", "hexaco", "personality trait", "personality psychology",
        "neuroticism", "extraversion", "conscientiousness", "agreeableness", "openness to experience",
        "dark triad", "dark tetrad", "narcissism", "psychopathy", "machiavellianism",
        "personality measurement", "personality psychometrics", "personality development",
        "personality disorder", "individual differences in personality",
    ],
    "intelligence cognitive abilities": [
        "general intelligence", "g factor", "cognitive ability", "cognitive abilities",
        "iq test", "intelligence test", "fluid intelligence", "crystallised intelligence",
        "cognitive ageing", "cognitive aging", "working memory capacity",
        "cognitive decline", "executive function", "processing speed",
        "scholastic aptitude", "educational achievement", "behavioural genetics intelligence",
    ],
    "relationship science": [
        "mate choice", "mate preference", "assortative mating", "romantic relationship",
        "adult attachment", "attachment style", "dyadic", "relationship satisfaction",
        "jealousy", "infidelity", "couple", "marital quality", "partnership",
        "APIM", "actor-partner", "relationship formation", "dating",
    ],
    "sex differences": [
        "sex differences", "sex difference", "gender differences in", "biological sex",
        "male-female differences", "sex gap", "sex-differentiated", "sex-specific",
        "cross-sex", "dimorphism", "sex-based", "sex-stratified",
    ],
    "evolutionary psychology": [
        "evolutionary psychology", "sexual selection", "parental investment",
        "kin selection", "adaptationist", "life history theory", "mating strategy",
        "evolved mechanism", "evolutionary basis", "fitness", "reproductive success",
        "natural selection human", "evolutionary perspective",
    ],
    "social psychology": [
        "social cognition", "social norm", "status hierarchy", "prejudice",
        "intergroup", "cooperation", "prosocial behaviour", "moral psychology",
        "group processes", "aggression", "social influence", "conformity",
        "implicit bias", "attitude change", "social identity",
    ],
    "weight management body composition": [
        "weight loss intervention", "weight management", "body composition",
        "fat mass", "lean mass", "obesity treatment", "adiposity",
        "energy intake", "energy expenditure", "caloric restriction",
        "dietary intervention weight", "weight maintenance", "BMI reduction",
        "bariatric", "anti-obesity",
    ],
    "cardiometabolic outcomes": [
        "cardiovascular disease", "CVD risk", "blood pressure reduction",
        "LDL cholesterol", "HDL cholesterol", "apoB", "triglycerides",
        "glycaemic control", "type 2 diabetes", "metabolic syndrome",
        "insulin resistance", "cardiometabolic", "coronary heart disease",
        "hypertension diet", "atherosclerosis diet",
    ],
    "dietary patterns foods": [
        "ultra-processed food", "dietary fibre", "dietary fiber", "protein intake",
        "saturated fat intake", "added sugar", "sodium intake", "alcohol consumption",
        "mediterranean diet", "DASH diet", "whole grain", "processed meat",
        "dietary pattern", "plant-based diet", "red meat consumption",
        "legume intake", "fruit and vegetable", "food consumption",
    ],
    "diet lifestyle longitudinal": [
        "prospective cohort diet", "diet and mortality", "dietary intake incident",
        "diet and cardiovascular", "diet and diabetes", "dose-response diet",
        "food substitution", "dietary substitution", "diet quality score",
        "healthy eating index", "all-cause mortality diet", "diet and cancer",
        "diet cohort", "longitudinal diet",
    ],
}


@dataclass
class AppConfig:
    TIME_WINDOW_DAYS: int = 14
    TOPICS: List[str] = field(default_factory=lambda: list(DEFAULT_TOPICS))
    JOURNAL_PRIORITIES: Dict[str, List[str]] = field(
        default_factory=lambda: {
            key: list(values) for key, values in DEFAULT_JOURNAL_PRIORITIES.items()
        }
    )
    OPEN_ACCESS_PRIORITY: bool = True
    MAX_PAPERS_PER_WEEK: int = 14
    MIN_PAPERS_PER_TOPIC: int = 1
    EXCLUDE: List[str] = field(
        default_factory=lambda: ["conference abstracts", "non-peer reviewed"]
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
