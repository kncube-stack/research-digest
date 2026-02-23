from __future__ import annotations

import re
from collections import Counter
from datetime import date
from typing import Dict, List, Optional

from .models import CandidatePaper


# ---------------------------------------------------------------------------
# Cluster tag mapping
# ---------------------------------------------------------------------------

CLUSTER_TAG_MAP = {
    "personality psychology": "Personality",
    "intelligence cognitive abilities": "Intelligence",
    "relationship science": "Relationships",
    "sex differences": "Sex differences",
    "evolutionary psychology": "Evo psych",
    "social psychology": "Social psych",
    "weight management body composition": "Weight loss",
    "cardiometabolic outcomes": "Cardiometabolic",
    "dietary patterns foods": "Dietary patterns",
    "diet lifestyle longitudinal": "Cohort",
}

STUDY_TYPE_TAG_MAP = {
    "randomized controlled trial": "RCT",
    "meta-analysis": "Meta-analysis",
    "systematic review": "Meta-analysis",
    "mendelian randomization": "MR",
    "cohort": "Cohort",
    "cross-sectional": "Cross-sectional",
}

NUTRITION_TOPICS = {
    "weight management body composition",
    "cardiometabolic outcomes",
    "dietary patterns foods",
    "diet lifestyle longitudinal",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> List[str]:
    text = " ".join(text.split())
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _truncate_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(" ,;:") + "..."


def _best_link(paper: CandidatePaper) -> str:
    if paper.doi:
        return f"https://doi.org/{paper.doi}"
    if paper.extra_links.get("publisher"):
        return paper.extra_links["publisher"] or ""
    if paper.extra_links.get("pmc"):
        return paper.extra_links["pmc"] or ""
    return paper.link or ""


def _is_nutrition_paper(paper: CandidatePaper) -> bool:
    return any(t in NUTRITION_TOPICS for t in paper.topic_tags)


def _pick_sentences(paper: CandidatePaper) -> Dict[str, List[str]]:
    sentences = _split_sentences(paper.abstract)

    method_sents = [
        s for s in sentences
        if re.search(
            r"\b(study|trial|cohort|analysis|investigated|examined|assessed|used|method|"
            r"dataset|randomized|randomised|participants?|patients?|recruited|enrolled|design)\b",
            s, re.IGNORECASE,
        )
    ]
    result_sents = [
        s for s in sentences
        if re.search(
            r"\b(found|results?|linked|associated|increased|decreased|reduced|improved|"
            r"risk|odds|effect|significant|no significant|difference|higher|lower|greater|"
            r"predicted|correlation|β|OR|HR|RR|CI)\b",
            s, re.IGNORECASE,
        )
    ]
    conclusion_sents = [
        s for s in sentences
        if re.search(
            r"\b(conclude|suggest|interpret|implications?|overall|therefore|may indicate|"
            r"highlight|underscore|support|challenge|warrant)\b",
            s, re.IGNORECASE,
        )
    ]

    return {
        "all": sentences,
        "method": method_sents,
        "result": result_sents,
        "conclusion": conclusion_sents,
    }


def _extract_sample(paper: CandidatePaper) -> str:
    """Try to pull a sample size / description from the abstract."""
    text = paper.abstract
    m = re.search(r"\b[Nn]\s*=\s*([\d,]+)", text)
    if m:
        return f"n = {m.group(1)}"
    m = re.search(r"([\d,]+)\s+(participants?|patients?|adults?|individuals?|men|women|subjects?)", text, re.IGNORECASE)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return "Not reported in abstract"


def _extract_timeframe(paper: CandidatePaper) -> Optional[str]:
    """Pull follow-up duration if present."""
    m = re.search(
        r"(\d+[\.\d]*)\s*(year|month|week|day)s?\s*(follow[\-\s]?up|follow[\-\s]?period|of follow)",
        paper.abstract, re.IGNORECASE,
    )
    if m:
        return f"{m.group(1)} {m.group(2)}s"
    return None


def _tags_for_paper(paper: CandidatePaper) -> List[str]:
    tags: List[str] = []

    for topic in paper.topic_tags:
        tag = CLUSTER_TAG_MAP.get(topic)
        if tag and tag not in tags:
            tags.append(tag)

    if _is_nutrition_paper(paper) and "Nutrition" not in tags:
        tags.append("Nutrition")

    study_tag = STUDY_TYPE_TAG_MAP.get(paper.study_type)
    if study_tag and study_tag not in tags:
        tags.append(study_tag)

    return tags


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_headline(paper: CandidatePaper, picked: Dict[str, List[str]]) -> str:
    """
    Build a complete-sentence summary of the article — one clear sentence that
    tells the reader what the study found (or asked), who the subjects were,
    and what the practical upshot is. Targets roughly 20–35 words.
    """
    # Prefer a result sentence that already contains a number (most concrete).
    result_with_num = [s for s in picked["result"] if re.search(r"\d", s)]
    result_sent = result_with_num[0] if result_with_num else (picked["result"][0] if picked["result"] else "")
    conclusion_sent = picked["conclusion"][0] if picked["conclusion"] else ""
    method_sent = picked["method"][0] if picked["method"] else ""

    # Strip boilerplate openers from whichever sentence we pick.
    def _clean(s: str) -> str:
        s = re.sub(r"[.!?]+$", "", s).strip()
        s = re.sub(
            r"^(results (indicate|show|suggest)|findings (indicate|show|suggest)|"
            r"we (found|observed|show|report)|this study (found|shows|demonstrates)|"
            r"the (study|analysis|results?) (found|showed|demonstrated|indicated))[,\s]+",
            "", s, flags=re.IGNORECASE,
        ).strip()
        return s[0].upper() + s[1:] if s else s

    # Try: combine a cleaned result sentence with a conclusion for a fuller picture.
    if result_sent and conclusion_sent:
        candidate = _clean(result_sent) + ". " + _clean(conclusion_sent) + "."
        words = candidate.split()
        if 15 <= len(words) <= 45:
            return candidate
        # Too long — just use the result sentence.
        return _clean(result_sent) + "."

    if result_sent:
        return _clean(result_sent) + "."

    if conclusion_sent:
        return _clean(conclusion_sent) + "."

    if method_sent:
        return _clean(method_sent) + "."

    # Final fallback: use the paper title as-is (already a sentence proxy).
    return paper.title if paper.title.endswith(".") else paper.title + "."


def _build_deck(paper: CandidatePaper, picked: Dict[str, List[str]]) -> str:
    """Deck: the question + main result in plain English."""
    question = ""
    result = ""

    if picked["method"]:
        question = picked["method"][0]
        question = re.sub(r"^(this study|we|the authors?|researchers?)\s+", "", question, flags=re.IGNORECASE).strip()
        question = question[0].upper() + question[1:] if question else ""

    if picked["result"]:
        result = picked["result"][0]
    elif picked["conclusion"]:
        result = picked["conclusion"][0]

    if question and result:
        return f"{_truncate_words(question, 30)} {_truncate_words(result, 35)}"
    elif result:
        return _truncate_words(result, 50)
    elif question:
        return _truncate_words(question, 50)
    return f"A new peer-reviewed study on {paper.topic_tags[0] if paper.topic_tags else 'this topic'}."


def _build_study_at_a_glance(paper: CandidatePaper, picked: Dict[str, List[str]]) -> str:
    lines = []

    design_label = {
        "randomized controlled trial": "Randomised controlled trial",
        "meta-analysis": "Meta-analysis",
        "systematic review": "Systematic review",
        "mendelian randomization": "Mendelian randomisation",
        "cohort": "Prospective cohort",
        "cross-sectional": "Cross-sectional survey",
        "case-control": "Case-control study",
        "unknown": "Not clearly stated",
    }.get(paper.study_type, paper.study_type.capitalize())

    lines.append(f"**Design:** {design_label}")
    lines.append(f"**Sample:** {_extract_sample(paper)}")

    iv = _truncate_words(" ".join(picked["method"][:1]) or "Not reported in abstract", 25)
    lines.append(f"**Exposure/IV:** {iv}")

    dv = _truncate_words(" ".join(picked["result"][:1]) or "Not reported in abstract", 25)
    lines.append(f"**Outcome/DV:** {dv}")

    timeframe = _extract_timeframe(paper)
    if timeframe:
        lines.append(f"**Timeframe:** {timeframe}")

    main_result = "Not reported in abstract"
    for s in picked["result"]:
        if re.search(r"\d", s):
            main_result = _truncate_words(s, 40)
            break
    if main_result == "Not reported in abstract" and picked["result"]:
        main_result = _truncate_words(picked["result"][0], 40)
    lines.append(f"**Main result:** {main_result}")

    return "\n".join(lines)


def _build_what_they_did(paper: CandidatePaper, picked: Dict[str, List[str]]) -> str:
    if not picked["method"]:
        if picked["all"]:
            return _truncate_words(" ".join(picked["all"][:3]), 120)
        return "Full methods were not available in accessible metadata."

    method_text = " ".join(picked["method"][:4])
    return _truncate_words(method_text, 120)


def _build_what_they_found(paper: CandidatePaper, picked: Dict[str, List[str]]) -> str:
    """
    Longer, richer discussion of results: up to ~300 words drawn from result,
    conclusion, and remaining abstract sentences. Structured as flowing prose
    paragraphs with a causation/association note and effect-size context.
    """
    # ── Gather as many relevant sentences as possible ──────────────────────
    result_sents = picked["result"]        # up to all of them
    conclusion_sents = picked["conclusion"]
    # Remaining abstract sentences not already in result or conclusion
    used = set(result_sents) | set(conclusion_sents)
    remaining = [s for s in picked["all"] if s not in used]

    # ── Para 1: the primary results (up to 5 sentences) ────────────────────
    para1_sents = result_sents[:5]
    if not para1_sents:
        para1_sents = remaining[:4]

    # ── Para 2: conclusions / interpretation (up to 3 sentences) ───────────
    para2_sents = conclusion_sents[:3]
    if not para2_sents and remaining:
        para2_sents = remaining[:2]

    # ── Para 3: any remaining detail (up to 2 sentences) ───────────────────
    # e.g. subgroup findings, sensitivity analyses mentioned in abstract
    used2 = set(para1_sents) | set(para2_sents)
    para3_sents = [s for s in (result_sents[5:] + remaining) if s not in used2][:2]

    paragraphs = []
    if para1_sents:
        paragraphs.append(" ".join(para1_sents))
    if para2_sents:
        paragraphs.append(" ".join(para2_sents))
    if para3_sents:
        paragraphs.append(" ".join(para3_sents))

    if not paragraphs:
        return "Results were not available in accessible metadata."

    # ── Causation / association note ───────────────────────────────────────
    is_causal = paper.study_type in {"randomized controlled trial", "mendelian randomization"}
    if is_causal:
        caution = (
            "**Interpreting causality:** The design ({}) supports causal inference more than "
            "observational alternatives, though residual confounding and compliance issues "
            "remain possible. Effect sizes should be interpreted alongside confidence intervals "
            "and clinical or practical significance thresholds.".format(
                "RCT" if paper.study_type == "randomized controlled trial" else "Mendelian randomisation"
            )
        )
    elif paper.study_type in {"meta-analysis", "systematic review"}:
        caution = (
            "**Interpreting the synthesis:** Pooled estimates carry the average uncertainty of "
            "the included studies. Pay attention to I² heterogeneity statistics and whether "
            "sensitivity analyses (e.g. leave-one-out) substantially change the headline finding."
        )
    elif paper.study_type == "cohort":
        caution = (
            "**Interpreting associations:** These are observational associations — the cohort "
            "design cannot rule out residual confounding by unmeasured lifestyle or genetic "
            "variables. The practical value lies in the effect magnitude and dose–response "
            "pattern rather than proof of causation."
        )
    elif paper.study_type == "cross-sectional":
        caution = (
            "**Interpreting associations:** Cross-sectional data capture a snapshot; the "
            "direction of causation between exposure and outcome cannot be established. "
            "Treat these findings as hypothesis-generating rather than confirmatory."
        )
    else:
        caution = (
            "**Interpreting associations:** These findings are observational. Causation cannot "
            "be inferred without experimental or quasi-experimental evidence."
        )

    body = "\n\n".join(paragraphs)
    return f"{body}\n\n{caution}"


def _build_why_it_matters(paper: CandidatePaper) -> str:
    bullets = []

    if paper.topic_tags:
        cluster = CLUSTER_TAG_MAP.get(paper.topic_tags[0], paper.topic_tags[0])
        bullets.append(f"Adds a fresh, peer-reviewed data point to the {cluster} literature.")

    if paper.study_type in {"meta-analysis", "systematic review"}:
        bullets.append(
            "Evidence synthesis shifts confidence more than a single study, "
            "assuming the included studies are methodologically sound."
        )
    elif paper.study_type == "randomized controlled trial":
        bullets.append("The RCT design targets causal inference, not merely correlation.")
    elif paper.study_type == "mendelian randomization":
        bullets.append(
            "Mendelian randomisation offers a quasi-causal test that is harder to confound "
            "than standard observational designs."
        )
    elif paper.study_type == "cohort":
        bullets.append("Long follow-up cohort data can reveal dose–response and substitution patterns over time.")

    if re.search(r"substitut|replac.{0,20}(with|by)", paper.abstract, re.IGNORECASE):
        bullets.append(
            "The substitution framing (what replaces what) is practically useful: "
            "it goes beyond 'food X is bad' to compare realistic dietary swaps."
        )

    if paper.open_access_status == "OPEN_ACCESS":
        bullets.append("Open access — you can verify methods and full results without paywall friction.")

    return "\n".join(f"- {b}" for b in bullets[:4])


def _build_caveats(paper: CandidatePaper, picked: Dict[str, List[str]]) -> str:
    bullets = []

    if paper.study_type == "cross-sectional":
        bullets.append("Cross-sectional design: temporal order is unknown; reverse causation is possible.")
    elif paper.study_type == "cohort":
        bullets.append(
            "Residual confounding is the primary limit in observational cohort work — "
            "dietary and lifestyle variables are difficult to isolate."
        )
    elif paper.study_type in {"meta-analysis", "systematic review"}:
        bullets.append(
            "Quality depends on the constituent studies; high heterogeneity undermines pooled estimates."
        )
    elif paper.study_type == "mendelian randomization":
        bullets.append(
            "MR assumes the genetic instruments affect the outcome only through the exposure (exclusion restriction); "
            "pleiotropy can violate this."
        )

    if re.search(r"self.report|questionnaire|recall|ffq|food frequency", paper.abstract, re.IGNORECASE):
        bullets.append(
            "Dietary/behavioural measurement relies on self-report, which is subject to recall bias and misclassification."
        )

    bullets.append(
        "Generalisability may be limited by sample characteristics (age, ethnicity, country) "
        "not fully described in accessible metadata."
    )

    if paper.open_access_status == "PAYWALLED":
        bullets.append(
            "Full text was paywalled during drafting — technical details (adjustment strategy, "
            "sensitivity analyses) require verification."
        )

    if not _is_nutrition_paper(paper):
        bullets.append(
            "Check whether primary and secondary outcomes are clearly distinguished, "
            "and whether reported effects survive correction for multiple comparisons."
        )

    return "\n".join(f"- {b}" for b in bullets[:5])


# ---------------------------------------------------------------------------
# End-matter (called once per digest, not per paper)
# ---------------------------------------------------------------------------

def build_end_matter(posts: List[Dict[str, object]]) -> str:
    """
    Generate the weekly end-matter block:
    - 5 recurring keywords
    - 3 emerging debates / contradictions
    - Gaps: what was expected but not seen
    """
    all_text = " ".join(
        str(p.get("what_they_found", "")) + " " + str(p.get("what_they_did", ""))
        for p in posts
    ).lower()

    words = re.findall(r"\b[a-z]{5,}\b", all_text)
    stop = {
        "which", "their", "there", "these", "those", "study", "paper", "found",
        "using", "among", "after", "about", "would", "could", "should", "being",
        "were", "have", "from", "with", "this", "that", "also", "more", "other",
        "between", "within", "across", "whether", "however", "although",
        "including", "reported", "results", "design", "abstract", "available",
        "sample", "cannot", "studies", "suggest", "indicate", "analysis",
        "alone", "inferred", "causation", "caveats", "associations",
    }
    filtered = [w for w in words if w not in stop]
    top_keywords = [word for word, _ in Counter(filtered).most_common(10)][:5]

    study_types = [str(p.get("study_type", "")) for p in posts]
    topic_tags_all: List[str] = []
    for p in posts:
        topic_tags_all.extend(p.get("tags", []))

    has_rct = "RCT" in topic_tags_all or "randomized controlled trial" in study_types
    has_cohort = "Cohort" in topic_tags_all or "cohort" in study_types
    has_mr = "MR" in topic_tags_all or "mendelian randomization" in study_types
    has_psych = any(t in topic_tags_all for t in ["Personality", "Intelligence", "Sex differences", "Evo psych"])
    has_nutrition = "Nutrition" in topic_tags_all

    debates = []
    if has_rct and has_cohort:
        debates.append(
            "RCT vs cohort discordance: evidence from both designs this week does not always point "
            "in the same direction — a reminder that effect sizes and populations differ across methodologies."
        )
    if has_mr:
        debates.append(
            "Causal inference via MR: ongoing debate about whether genetic instruments are truly valid "
            "or whether pleiotropy inflates apparent causal estimates."
        )
    if has_psych:
        debates.append(
            "Replication and effect size inflation in psychology: a recurring tension between "
            "headline-level findings and robustness across independent samples."
        )
    if has_nutrition and len(debates) < 3:
        debates.append(
            "Dietary pattern vs single-nutrient approaches: tension between food-based and "
            "nutrient-based analytical frameworks continues across this week's nutrition papers."
        )
    while len(debates) < 3:
        debates.append(
            "Measurement heterogeneity: differences in how exposure and outcome variables are "
            "operationalised across studies make direct comparison difficult."
        )

    topic_tag_set = set(topic_tags_all)
    gaps = []
    expected = {
        "Personality": "personality × health outcomes longitudinal data",
        "Intelligence": "cognitive ageing intervention or RCT",
        "Relationships": "dyadic / APIM study of couples",
        "Sex differences": "cross-cultural replication of sex-difference findings",
        "Evo psych": "pre-registered evolutionary psychology study",
        "Nutrition": "large substitution-analysis cohort study",
        "Cardiometabolic": "diet × exercise interaction RCT",
        "Weight loss": "long-term (≥2 year) weight maintenance trial",
    }
    for tag, description in expected.items():
        if tag not in topic_tag_set:
            gaps.append(description)
    if not gaps:
        gaps.append("No notable gaps this week — coverage spanned all tracked clusters.")

    lines = [
        "---",
        "## Weekly end-matter",
        "",
        "### Recurring keywords this week",
        ", ".join(top_keywords) if top_keywords else "Insufficient text for keyword extraction.",
        "",
        "### Emerging debates / contradictions",
    ]
    for i, debate in enumerate(debates[:3], 1):
        lines.append(f"{i}. {debate}")

    lines += [
        "",
        "### Gaps: expected but not seen this week",
    ]
    for gap in gaps[:4]:
        lines.append(f"- {gap}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def render_post_object(
    paper: CandidatePaper,
    summary_min_words: int = 0,
    summary_max_words: int = 0,
) -> Dict[str, object]:
    picked = _pick_sentences(paper)

    pub_date = paper.publication_date.isoformat() if isinstance(paper.publication_date, date) else ""
    authors = paper.authors if paper.authors.strip().lower() not in {"", "unknown"} else "Unknown"
    doi = paper.doi or ""
    link = _best_link(paper)
    tags = _tags_for_paper(paper)

    headline = _build_headline(paper, picked)
    deck = _build_deck(paper, picked)
    study_at_a_glance = _build_study_at_a_glance(paper, picked)
    what_they_did = _build_what_they_did(paper, picked)
    what_they_found = _build_what_they_found(paper, picked)
    why_it_matters = _build_why_it_matters(paper)
    caveats = _build_caveats(paper, picked)
    read_the_paper = f"DOI: {doi}\nLink: {link}" if doi else f"Link: {link}"

    return {
        "headline": headline,
        "deck": deck,
        "study_at_a_glance": study_at_a_glance,
        "what_they_did": what_they_did,
        "what_they_found": what_they_found,
        "why_it_matters": why_it_matters,
        "caveats_and_alternative_explanations": caveats,
        "read_the_paper": read_the_paper,
        "tags": tags,
        # Metadata fields kept for store / UI compatibility.
        "paper_title": paper.title,
        "authors": authors,
        "journal": paper.journal,
        "publication_date": pub_date,
        "study_type": paper.study_type,
        "open_access_status": paper.open_access_status,
        "doi": doi,
        "topic_tags": paper.topic_tags,
        "extra_links": {
            "publisher": paper.extra_links.get("publisher"),
            "pdf": paper.extra_links.get("pdf"),
            "pubmed": paper.extra_links.get("pubmed"),
            "pmc": paper.extra_links.get("pmc"),
        },
    }
