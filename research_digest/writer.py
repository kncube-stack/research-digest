from __future__ import annotations

import re
from datetime import date
from typing import Dict, List

from .models import CandidatePaper

SUMMARY_MIN_WORDS = 420
SUMMARY_MAX_WORDS = 780


def _split_sentences(text: str) -> List[str]:
    text = " ".join(text.split())
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _clean_sentence(text: str) -> str:
    return re.sub(r"^(background|methods?|results?|conclusions?)\s*[:.-]\s*", "", text, flags=re.IGNORECASE).strip()


def _truncate_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(" ,;:") + "..."


def _word_count(text: str) -> int:
    return len(text.split())


def _topic_phrase(paper: CandidatePaper) -> str:
    tags = [t for t in paper.topic_tags if t]
    if not tags:
        return "your tracked themes"
    if len(tags) == 1:
        return tags[0]
    return f"{tags[0]} and {tags[1]}"


def _plainify(text: str) -> str:
    replacements = {
        "was associated with": "was linked to",
        "were associated with": "were linked to",
        "is associated with": "is linked to",
        "are associated with": "are linked to",
        "statistically significant": "unlikely to be due to chance",
        "participants": "people in the study",
        "subjects": "people in the study",
    }
    out = text
    for old, new in replacements.items():
        out = re.sub(old, new, out, flags=re.IGNORECASE)
    return out


def _best_link(paper: CandidatePaper) -> str:
    if paper.extra_links.get("pdf"):
        return paper.extra_links["pdf"] or ""
    if paper.extra_links.get("pmc"):
        return paper.extra_links["pmc"] or ""
    if paper.extra_links.get("publisher"):
        return paper.extra_links["publisher"] or ""
    if paper.doi:
        return f"https://doi.org/{paper.doi}"
    return paper.link or ""


def _headline(paper: CandidatePaper, takeaway: str) -> str:
    title = takeaway.rstrip(".") if takeaway else paper.title
    title = re.sub(r"\s+", " ", title).strip()
    if title:
        title = title[0].upper() + title[1:]
    return _truncate_words(title or paper.title, 16)


def _pick_sentences(paper: CandidatePaper) -> Dict[str, List[str]]:
    sentences = [_clean_sentence(s) for s in _split_sentences(paper.abstract)]

    method_sents = [
        s
        for s in sentences
        if re.search(
            r"\b(study|trial|cohort|analysis|investigated|examined|assessed|used|method|dataset|randomized|randomised|participants?|patients?)\b",
            s,
            re.IGNORECASE,
        )
    ]

    result_sents = [
        s
        for s in sentences
        if re.search(
            r"\b(found|results|linked|associated|increased|decreased|reduced|improved|risk|odds|effect|significant|no significant|difference)\b",
            s,
            re.IGNORECASE,
        )
    ]

    conclusion_sents = [
        s
        for s in sentences
        if re.search(r"\b(conclude|suggest|interpret|implications|overall|therefore|may indicate)\b", s, re.IGNORECASE)
    ]

    return {
        "all": sentences,
        "method": method_sents,
        "result": result_sents,
        "conclusion": conclusion_sents,
    }


def _one_sentence_takeaway(paper: CandidatePaper) -> str:
    picked = _pick_sentences(paper)
    if picked["result"]:
        return _truncate_words(_plainify(picked["result"][0]), 30)
    if picked["all"]:
        return _truncate_words(_plainify(picked["all"][0]), 30)
    return "A newly published paper in your topic stack, but accessible metadata did not include enough detail for a strong one-line finding."


def _design_reader_note(study_type: str) -> str:
    if study_type in {"cross-sectional", "case-control", "cohort"}:
        return "Design-wise, this is observational work, so the strongest reading is about patterns and probability rather than direct causal proof."
    if study_type in {"randomized controlled trial", "mendelian randomization"}:
        return "The design is built to get closer to causal interpretation than a simple correlation study, although it still carries assumptions and practical limits."
    if study_type in {"meta-analysis", "systematic review"}:
        return "Because this is evidence synthesis, it can shift confidence more than one isolated study, but only if the included studies are methodologically solid."
    if study_type in {"animal", "mechanistic"}:
        return "This style of evidence is usually strongest for mechanism-building, and weaker for immediate real-world claims about human outcomes."
    return "Interpretation still depends heavily on sampling, measurement quality, and whether findings replicate in independent datasets."


def _access_reader_note(paper: CandidatePaper) -> str:
    if paper.open_access_status == "OPEN_ACCESS":
        return "The paper appears open access, which means you can verify details quickly and read beyond the abstract without paywall friction."
    if paper.open_access_status == "PAYWALLED":
        return "The paper appears paywalled, so this draft leans on abstract-level evidence and intentionally avoids overconfident detail claims."
    return "Open-access status is unclear from metadata alone, so it is worth checking the link directly before sharing hard conclusions."


def _build_summary(
    paper: CandidatePaper,
    summary_min_words: int = SUMMARY_MIN_WORDS,
    summary_max_words: int = SUMMARY_MAX_WORDS,
) -> str:
    topic_phrase = _topic_phrase(paper)

    if not paper.abstract:
        summary = (
            f"This paper, published in {paper.journal}, falls squarely within your {topic_phrase} watchlist, but accessible metadata did not include an extractable abstract.\n\n"
            "That matters because without abstract-level methods and results, any confident claim about effect size, certainty, or practical impact would risk overreach. "
            "So this draft is intentionally conservative: it treats the paper as a high-priority lead rather than a completed interpretation.\n\n"
            "What is still useful right now is triage. First, the journal context and recency suggest this is worth attention in your weekly evidence flow. "
            "Second, the best-link pathway is already attached so you can move directly to source verification.\n\n"
            "At this stage, the most responsible interpretation is process-oriented rather than claim-oriented. "
            "In other words: use this entry to decide whether the paper deserves immediate full-text reading, not to draw clinical or behavioural conclusions from limited metadata.\n\n"
            "If you open the full text, the highest-value checks are straightforward: sample composition, primary endpoint definition, adjustment strategy, and whether the conclusions track the reported data rather than exploratory side analyses.\n\n"
            "Also check whether the design is observational, interventional, or evidence synthesis, because that one detail changes how strongly you should treat any practical implication. "
            "If effect sizes are reported, compare relative and absolute framing, and note whether uncertainty intervals are wide enough to keep conclusions provisional.\n\n"
            "In short, this is a credible signal to follow up, but not yet a paper to over-interpret from metadata alone. "
            "Its value in this digest is prioritisation: it keeps your radar aligned with what is newly published, while preserving a high bar for evidence claims."
        )
        if _word_count(summary) < 300:
            summary += (
                "\n\n"
                "Editorially, the safest next move is simple: open the source, verify the methods section first, then evaluate whether the headline claim survives scrutiny of endpoints, adjustments, and subgroup handling."
            )
        return _truncate_words(summary, summary_max_words)

    picked = _pick_sentences(paper)
    method_line = _plainify(" ".join(picked["method"][:3]) or " ".join(picked["all"][:2]))
    result_line = _plainify(" ".join(picked["result"][:4]) or " ".join(picked["all"][1:4]))
    conclusion_line = _plainify(" ".join(picked["conclusion"][:2]))

    if not method_line:
        method_line = "From available metadata, the study question and design framing are clear, but methods are only partially visible."
    if not result_line:
        result_line = "The abstract gives directional signal, but limited quantitative texture for full confidence on magnitude."
    if not conclusion_line:
        conclusion_line = "The authors frame the finding as an incremental advance rather than definitive closure on the question."

    paragraphs = [
        (
            f"This week\'s paper from {paper.journal} tackles a question at the heart of {topic_phrase}. "
            "For a science-magazine reader, the key point is not just whether the finding sounds interesting, "
            "but how much evidential weight it should carry in the broader literature."
        ),
        (
            "What the researchers did: "
            f"{method_line} "
            "That framing helps anchor interpretation, because methods usually determine whether a result is likely to travel beyond one sample or setting."
        ),
        (
            "What they found: "
            f"{result_line} "
            "Read plainly, this is best treated as a structured signal rather than a headline-level final answer, "
            "especially when full technical appendices are not visible in metadata feeds."
        ),
        (
            "How the authors interpret it: "
            f"{conclusion_line} "
            f"{_design_reader_note(paper.study_type)}"
        ),
        (
            "Why this is useful for your weekly tracking: the paper adds an up-to-date data point in a topic you actively monitor, "
            "and it gives you concrete direction for what to verify next when reading in full: endpoint hierarchy, robustness checks, and population boundaries. "
            f"{_access_reader_note(paper)}"
        ),
    ]

    summary = "\n\n".join(paragraphs)

    expansion_blocks = [
        "A practical reading strategy is to separate the central finding from the narrative wrapper around it: keep what was measured, keep what was tested, and hold conclusions to the evidence rather than to headline phrasing.",
        "If this topic already has mixed prior evidence, the best interpretation is cumulative, not dramatic. One new study can nudge confidence in a direction, but it rarely closes a contested question on its own.",
        "For decisions in the real world, this paper is best treated as a ranked signal in your weekly queue: strong enough to read in full, useful enough to discuss, and still dependent on replication and transparent methods.",
        "External validity is a key checkpoint: even well-run studies can fail to generalise if sample characteristics, baseline risk, or social context differ meaningfully from the populations you care about.",
        "Another useful check is endpoint hierarchy. Strong papers foreground primary outcomes and treat secondary or exploratory findings with proportionate caution rather than promoting them as equivalent headline results.",
        "Adjustment strategy matters too: when claims survive thoughtful control for plausible confounders, confidence increases; when estimates move sharply across models, uncertainty should remain central in interpretation.",
        "Where possible, read this alongside at least one prior paper on the same question. The strongest understanding comes from convergence patterns across studies, not from any single result in isolation.",
        "In short, this article-length summary is designed to keep the signal clear and the certainty calibrated: informative for staying current, but disciplined about what the underlying evidence can and cannot support.",
    ]

    idx = 0
    while _word_count(summary) < summary_min_words and idx < len(expansion_blocks):
        summary += "\n\n" + expansion_blocks[idx]
        idx += 1

    if _word_count(summary) < summary_min_words:
        summary += (
            "\n\n"
            "Final editorial note: treat this as a robust weekly briefing draft rather than a definitive clinical or policy recommendation. "
            "Its value is in rapid orientation to new evidence, clear statement of what is known, and explicit acknowledgement of what still needs full-text scrutiny or independent replication."
        )

    return _truncate_words(summary, summary_max_words)


def _why_it_matters(paper: CandidatePaper) -> str:
    lines = [
        "- It gives you a fresh, peer-reviewed signal in one of your core interest areas.",
        "- The write-up is optimized for informed readers who want nuance without dense academic prose.",
    ]

    if paper.study_type in {"meta-analysis", "systematic review"}:
        lines.append("- Evidence synthesis can shift confidence more than a single isolated study when methods are strong.")
    elif paper.study_type in {"randomized controlled trial", "mendelian randomization"}:
        lines.append("- The design aims for stronger causal insight than basic observational comparisons.")
    else:
        lines.append("- It helps spotlight where the field is moving and what deserves full-text follow-up first.")

    if paper.open_access_status == "OPEN_ACCESS":
        lines.append("- Open access means faster verification and easier sharing with collaborators.")

    return "\n".join(lines[:4])


def _limitations(paper: CandidatePaper) -> str:
    lines = []

    if paper.study_type in {"cross-sectional", "case-control", "cohort"}:
        lines.append("- Observational designs can reveal links but cannot, by themselves, prove causation.")
    elif paper.study_type in {"animal", "mechanistic"}:
        lines.append("- Mechanistic findings may not translate directly into real-world human outcomes.")
    elif paper.study_type == "theory":
        lines.append("- Conceptual papers depend on argument strength rather than newly collected primary data.")

    if paper.open_access_status == "PAYWALLED":
        lines.append("- Full text was not openly accessible during drafting, so detail depth is constrained.")

    if not paper.abstract:
        lines.append("- No abstract text was available through queried metadata, so quantitative detail was intentionally limited.")
    else:
        lines.append("- Critical technical details still require full-text checks, including selection criteria and sensitivity analyses.")

    lines.append("- Generalisability may be limited by sample, context, and measurement choices not fully visible in metadata feeds.")

    return "\n".join(lines[:5])


def render_post_object(
    paper: CandidatePaper,
    summary_min_words: int = SUMMARY_MIN_WORDS,
    summary_max_words: int = SUMMARY_MAX_WORDS,
) -> Dict[str, object]:
    takeaway = _one_sentence_takeaway(paper)
    headline = _headline(paper, takeaway)

    pub_date = paper.publication_date.isoformat() if isinstance(paper.publication_date, date) else ""
    authors = paper.authors if paper.authors.strip().lower() not in {"", "unknown"} else "Unknown"

    return {
        "topic_tags": paper.topic_tags,
        "title": headline,
        "paper_title": paper.title,
        "authors": authors,
        "journal": paper.journal,
        "publication_date": pub_date,
        "study_type": paper.study_type,
        "one_sentence_takeaway": takeaway,
        "summary": _build_summary(
            paper,
            summary_min_words=summary_min_words,
            summary_max_words=summary_max_words,
        ),
        "why_it_matters": _why_it_matters(paper),
        "limitations_and_caveats": _limitations(paper),
        "open_access_status": paper.open_access_status,
        "best_link": _best_link(paper),
        "doi": paper.doi or "",
        "extra_links": {
            "publisher": paper.extra_links.get("publisher"),
            "pdf": paper.extra_links.get("pdf"),
            "pubmed": paper.extra_links.get("pubmed"),
            "pmc": paper.extra_links.get("pmc"),
        },
    }
