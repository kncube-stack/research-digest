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
            r"highlight|underscore|support|challenge|warrant|remains?|demonstrate|"
            r"in conclusion|in summary|taken together|these (findings|results)|"
            r"our (findings|results)|collectively)\b",
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
    6–8 word grammatical sentence — a punchy, complete thought that captures
    the study's core finding. Think magazine cover line: subject + verb + object.

    Strategy:
    1. Find the key conclusion or result sentence.
    2. Extract a subject-verb-object clause from it (up to 8 words).
    3. Fall back to a reworked version of the paper title if the abstract
       doesn't yield a clean short clause.
    """
    def _clean(s: str) -> str:
        s = re.sub(r"[.!?]+$", "", s).strip()
        # Strip leading boilerplate openers — iteratively so chained openers are removed.
        for _ in range(3):
            s = re.sub(
                r"^(results? (indicate|show|suggest|demonstrate)|"
                r"findings (indicate|show|suggest|demonstrate)|"
                r"these (results?|findings) (indicate|show|suggest|demonstrate|support)|"
                r"our (results?|findings) (indicate|show|suggest|demonstrate)|"
                r"we (found|observed|show|report|demonstrate)|"
                r"this study (found|shows|demonstrates)|"
                r"the (study|analysis|results?) (found|showed|demonstrated|indicated)|"
                r"overall[,\s]+|therefore[,\s]+|together[,\s]+|"
                r"taken together[,\s]+|in (summary|conclusion)[,\s]+)[,\s]*",
                "", s, flags=re.IGNORECASE,
            ).strip()
        s = re.sub(r"^(that|which)\s+", "", s, flags=re.IGNORECASE).strip()
        return s[0].upper() + s[1:] if s else s

    # Prefer conclusion sentences — they tend to already be compact summaries.
    # Avoid sentences that are dominated by numbers/stats (not readable as headlines).
    def _is_number_heavy(s: str) -> bool:
        words = s.split()
        return len(words) > 0 and sum(bool(re.search(r"\d", w)) for w in words) / len(words) > 0.35

    conclusion_clean = [s for s in picked["conclusion"] if not _is_number_heavy(s)]
    result_clean = [s for s in picked["result"] if not _is_number_heavy(s)]
    result_with_num = [s for s in picked["result"] if re.search(r"\d", s) and not _is_number_heavy(s)]

    candidates = (
        conclusion_clean
        or result_clean
        or result_with_num
        or picked["result"]
        or picked["method"]
        or picked["all"]
    )

    for sent in candidates:
        cleaned = _clean(sent)
        if not cleaned:
            continue

        # Try to find a subject+verb clause ending at a comma, semicolon,
        # or natural break within the first 8 words.
        # Split on comma or semicolon first — these often delimit compact clauses.
        clause = re.split(r"[,;]", cleaned)[0].strip()
        words = clause.split()
        if 6 <= len(words) <= 8:
            headline = clause
        elif len(words) > 8:
            # Trim to 8 words, back off trailing prepositions/articles.
            weak_endings = {"a", "an", "the", "in", "of", "for", "and",
                            "or", "to", "with", "on", "at", "by", "from",
                            "but", "as", "if", "its", "their"}
            end = 8
            while end > 5 and words[end - 1].lower() in weak_endings:
                end -= 1
            headline = " ".join(words[:end])
        else:
            # Clause is shorter than 6 words — try the full cleaned sentence.
            all_words = cleaned.split()
            if len(all_words) >= 6:
                weak_endings = {"a", "an", "the", "in", "of", "for", "and",
                                "or", "to", "with", "on", "at", "by", "from",
                                "but", "as", "if", "its", "their"}
                end = min(8, len(all_words))
                while end > 5 and all_words[end - 1].lower() in weak_endings:
                    end -= 1
                headline = " ".join(all_words[:end])
            else:
                continue  # Try the next candidate sentence.

        # If the result starts with a gerund or infinitive (no subject), prepend "Evidence supports".
        first_word = headline.split()[0].rstrip(".,") if headline.split() else ""
        if first_word.lower() in {"recommending", "using", "taking", "including",
                                   "replacing", "adding", "reducing", "increasing",
                                   "adopting", "following", "eating", "avoiding"}:
            headline = "Evidence supports " + headline[0].lower() + headline[1:]
            # Re-trim to 8 words.
            words2 = headline.split()
            if len(words2) > 8:
                headline = " ".join(words2[:8])

        # Capitalise and end with a period.
        headline = headline[0].upper() + headline[1:]
        if not headline.endswith((".", "!", "?")):
            headline += "."
        return headline

    # Final fallback: take the first 7 words of the paper title.
    title_words = paper.title.split()
    fallback = " ".join(title_words[:7]) if len(title_words) >= 6 else paper.title
    fallback = fallback[0].upper() + fallback[1:]
    if not fallback.endswith((".", "!", "?")):
        fallback += "."
    return fallback


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
    """
    Magazine-style methods paragraph. Sets the scene: who was studied, how,
    for how long, and what the researchers were trying to answer. Reads as
    flowing prose, not a bullet list.
    """
    method_sents = picked["method"][:5]
    if not method_sents:
        method_sents = picked["all"][:4]
    if not method_sents:
        return "Full methods were not available in the accessible abstract."

    # Design label for inline use
    design_prose = {
        "randomized controlled trial": "a randomised controlled trial",
        "meta-analysis": "a meta-analysis",
        "systematic review": "a systematic review and meta-analysis",
        "mendelian randomization": "a Mendelian randomisation study",
        "cohort": "a prospective cohort study",
        "cross-sectional": "a cross-sectional survey",
        "case-control": "a case-control study",
    }.get(paper.study_type, "a peer-reviewed study")

    sample = _extract_sample(paper)
    timeframe = _extract_timeframe(paper)

    # Opening sentence frames the design and scale.
    opening = f"The researchers conducted {design_prose}"
    if sample != "Not reported in abstract":
        opening += f" involving {sample}"
    if timeframe:
        opening += f" with a follow-up period of {timeframe}"
    opening += "."

    # Body: all method sentences joined as prose.
    body = " ".join(method_sents)

    return f"{opening} {body}"


def _build_what_they_found(paper: CandidatePaper, picked: Dict[str, List[str]]) -> str:
    """
    The main body of the article — magazine-quality prose that walks the reader
    through the results as a science journalist would. Three paragraphs:
      1. Primary results in full (all available result sentences).
      2. Authors' interpretation / conclusions in context.
      3. Nuance: subgroup differences, dose–response, secondary outcomes, or
         remaining abstract content that enriches the picture.
    Closes with a design-specific paragraph on how to read the evidence.
    """
    result_sents = picked["result"]
    conclusion_sents = picked["conclusion"]
    used = set(result_sents) | set(conclusion_sents)
    remaining = [s for s in picked["all"] if s not in used]

    # ── Para 1: primary results ────────────────────────────────────────────
    para1_sents = result_sents[:6]
    if not para1_sents:
        para1_sents = remaining[:4]

    # ── Para 2: conclusions / authors' interpretation ──────────────────────
    para2_sents = conclusion_sents[:4]
    if not para2_sents and remaining:
        para2_sents = remaining[:3]

    # ── Para 3: additional texture — subgroups, sensitivity, secondary outcomes
    used2 = set(para1_sents) | set(para2_sents)
    extra = [s for s in (result_sents[6:] + remaining) if s not in used2]
    para3_sents = extra[:3]

    # ── Assemble paragraphs ────────────────────────────────────────────────
    paragraphs: List[str] = []

    if para1_sents:
        paragraphs.append(" ".join(para1_sents))

    if para2_sents:
        # Transition intro varies by study type for natural prose flow.
        transitions = {
            "randomized controlled trial": "The authors interpret these effects as follows:",
            "meta-analysis": "Pooling evidence across studies, the authors conclude:",
            "systematic review": "Across the body of evidence reviewed, the authors note:",
            "mendelian randomization": "Using genetic proxies to tease apart causation, the researchers argue:",
            "cohort": "Looking at the longer picture, the researchers conclude:",
            "cross-sectional": "Drawing on the cross-sectional data, the authors suggest:",
        }
        transition = transitions.get(paper.study_type, "The authors interpret these findings as follows:")
        paragraphs.append(f"{transition} " + " ".join(para2_sents))

    if para3_sents:
        paragraphs.append(
            "Further detail from the abstract: " + " ".join(para3_sents)
        )

    if not paragraphs:
        return "Results were not available in the accessible abstract."

    # ── Design-specific evidence-reading paragraph ─────────────────────────
    if paper.study_type == "randomized controlled trial":
        reading_guide = (
            "**How to read this evidence:** A randomised controlled trial is the closest "
            "science gets to a controlled experiment in humans. Participants were assigned "
            "to conditions by chance, which distributes known and unknown confounders "
            "across groups. That said, real-world compliance, blinding limitations, and "
            "short trial durations can all shrink or distort the true effect. When reading "
            "the headline number, look for the confidence interval — a wide interval "
            "signals uncertainty even if the point estimate looks impressive. And ask "
            "whether the outcome measured is the one that matters clinically or practically."
        )
    elif paper.study_type == "mendelian randomization":
        reading_guide = (
            "**How to read this evidence:** Mendelian randomisation exploits the random "
            "inheritance of genetic variants as natural instruments for an exposure — "
            "a clever workaround for the confounding that plagues standard observational "
            "research. Because genes are set at conception, they cannot be caused by "
            "lifestyle choices, making reverse causation unlikely. The key caveat is "
            "pleiotropy: if a genetic variant affects the outcome through a pathway other "
            "than the exposure of interest, the causal estimate is biased. Sensitivity "
            "analyses (weighted median, MR-Egger) are designed to detect this — check "
            "whether the paper reports them."
        )
    elif paper.study_type in {"meta-analysis", "systematic review"}:
        reading_guide = (
            "**How to read this evidence:** A meta-analysis or systematic review synthesises "
            "many studies into a single pooled estimate, which carries more statistical "
            "weight than any individual finding. But its quality is only as good as the "
            "studies it includes. Look at the heterogeneity statistic (I²): values above "
            "50–75% suggest the studies are measuring meaningfully different things, and "
            "the pooled number becomes harder to interpret. Publication bias — the tendency "
            "for positive results to appear in journals more often than null results — "
            "can also inflate pooled effect sizes. Funnel plots and Egger's test are "
            "standard checks; note whether the paper addresses them."
        )
    elif paper.study_type == "cohort":
        reading_guide = (
            "**How to read this evidence:** Prospective cohort studies follow people over "
            "time, recording exposures before outcomes occur. This rules out reverse "
            "causation — you know the exposure came first. What cohort studies cannot do "
            "is rule out confounding: people who eat more vegetables also tend to exercise "
            "more, smoke less, and earn more. Researchers adjust for known confounders, "
            "but unmeasured variables always remain. The practical read: a large, "
            "well-adjusted cohort showing a consistent dose–response relationship (more "
            "exposure → more or less outcome in a graduated way) is more persuasive than "
            "a binary high-vs-low comparison with modest adjustment."
        )
    elif paper.study_type == "cross-sectional":
        reading_guide = (
            "**How to read this evidence:** A cross-sectional study is a snapshot — "
            "exposure and outcome are measured at the same moment, so there is no way "
            "to know which came first. A person's diet today may reflect their health "
            "status as much as it influences it. That makes reverse causation a standing "
            "concern. These studies are best read as scene-setters: they can identify "
            "associations worth following up with longitudinal or experimental designs, "
            "but they cannot confirm causation on their own."
        )
    else:
        reading_guide = (
            "**How to read this evidence:** The study design limits causal claims — "
            "associations identified here should be treated as hypotheses for future "
            "experimental or quasi-experimental investigation. Look at sample size, "
            "adjustment strategy, and whether findings replicate in independent cohorts "
            "before updating beliefs substantially."
        )

    body = "\n\n".join(paragraphs)
    return f"{body}\n\n{reading_guide}"


def _build_why_it_matters(paper: CandidatePaper) -> str:
    """
    Magazine-style 'so what?' section — flowing prose that explains why this
    paper deserves the reader's attention, what gap it fills, and what it
    might change in practice or in the scientific conversation.
    """
    cluster = CLUSTER_TAG_MAP.get(paper.topic_tags[0], paper.topic_tags[0]) if paper.topic_tags else "this field"

    # ── Design-specific significance statement ─────────────────────────────
    if paper.study_type in {"meta-analysis", "systematic review"}:
        design_note = (
            f"In the {cluster} literature, individual studies accumulate slowly and "
            f"often point in conflicting directions. A meta-analysis or systematic review "
            f"is the mechanism by which the field reconciles those conflicts — it pools "
            f"the evidence and, when done well, arrives at an estimate more reliable than "
            f"any single experiment. A new synthesis therefore shifts the evidentiary "
            f"baseline in a way that a single study simply cannot."
        )
    elif paper.study_type == "randomized controlled trial":
        design_note = (
            f"Most of what we know about {cluster} comes from observational data — "
            f"associations that could reflect confounding as much as genuine effects. "
            f"A randomised trial cuts through that ambiguity by assigning participants "
            f"to conditions by chance, making it the closest approximation to a controlled "
            f"experiment available in human research. When an RCT produces a clear result, "
            f"it carries more evidential weight than a dozen cohort studies pointing the "
            f"same way."
        )
    elif paper.study_type == "mendelian randomization":
        design_note = (
            f"Establishing causation in {cluster} research is notoriously difficult: "
            f"people who differ on one variable tend to differ on many. Mendelian "
            f"randomisation sidesteps this by using genetic variants — fixed at birth "
            f"and unaffected by lifestyle — as proxies for the exposure of interest. "
            f"It is not a perfect instrument, but it adds a qualitatively different kind "
            f"of evidence to a literature otherwise dominated by correlational data."
        )
    elif paper.study_type == "cohort":
        design_note = (
            f"Large prospective cohorts are the workhorses of {cluster} research. "
            f"By tracking the same people over years, they can observe how small "
            f"differences in behaviour or biology compound into substantially different "
            f"outcomes. They are especially useful for estimating dose–response "
            f"relationships and for testing whether an effect holds across subgroups — "
            f"questions that shorter trials cannot answer."
        )
    else:
        design_note = (
            f"This study adds a peer-reviewed data point to the {cluster} literature "
            f"at a time when the evidence base is still being assembled. Even descriptive "
            f"or cross-sectional work matters when it identifies patterns that deserve "
            f"experimental follow-up."
        )

    # ── Substitution framing note (nutrition context) ──────────────────────
    substitution_note = ""
    if re.search(r"substitut|replac.{0,20}(with|by)", paper.abstract, re.IGNORECASE):
        substitution_note = (
            " The substitution framing is worth highlighting: rather than simply "
            "asking whether food X is 'bad', the study asks what happens when you "
            "swap it for food Y — a more realistic and actionable question for "
            "everyday dietary decisions."
        )

    # ── Open access note ───────────────────────────────────────────────────
    oa_note = ""
    if paper.open_access_status == "OPEN_ACCESS":
        oa_note = (
            " The paper is open access, so anyone can examine the methods, "
            "supplementary tables, and raw effect sizes directly — no paywall required."
        )

    return design_note + substitution_note + oa_note


def _build_caveats(paper: CandidatePaper, picked: Dict[str, List[str]]) -> str:
    """
    Magazine-style caveats section — written as flowing prose that honestly
    engages with the study's limitations without dismissing the findings.
    Reads like a critical friend explaining what to watch out for.
    """
    paras: List[str] = []

    # ── Primary design caveat ──────────────────────────────────────────────
    if paper.study_type == "cross-sectional":
        paras.append(
            "The most important limitation here is the snapshot design. Because exposure "
            "and outcome are measured simultaneously, there is no way to establish which "
            "came first. A person's current diet, mood, or behaviour may well be a "
            "consequence of their health status rather than a cause of it — a problem "
            "called reverse causation. Cross-sectional findings are best treated as "
            "signals that warrant longitudinal follow-up, not as evidence of effect."
        )
    elif paper.study_type == "cohort":
        paras.append(
            "Even the best-designed cohort study cannot fully escape confounding. People "
            "who score high on one dietary or behavioural variable tend to score differently "
            "on dozens of others — income, education, sleep, exercise, stress — and "
            "researchers can only adjust for variables they have measured. Whatever remains "
            "unmeasured can silently inflate or deflate the apparent effect. This is "
            "especially true in nutrition and lifestyle research, where the things people "
            "do are deeply intertwined. A finding that survives multiple adjustments and "
            "dose–response testing is more persuasive, but residual confounding can never "
            "be ruled out entirely."
        )
    elif paper.study_type in {"meta-analysis", "systematic review"}:
        paras.append(
            "A meta-analysis is only as strong as its constituent studies. If the "
            "literature it draws on is dominated by small trials, poor adjustment, or "
            "publication bias — the tendency for positive results to reach journals more "
            "readily than null ones — the pooled estimate will inherit those flaws. "
            "Heterogeneity is the key diagnostic: when I² is high, the studies are "
            "measuring something meaningfully different from each other, and the pooled "
            "number becomes an average of apples and oranges. Look for whether the "
            "authors run sensitivity analyses that remove influential studies or restrict "
            "to higher-quality designs."
        )
    elif paper.study_type == "mendelian randomization":
        paras.append(
            "Mendelian randomisation is an elegant design, but it rests on assumptions "
            "that can be violated. The most critical is the exclusion restriction: "
            "the genetic instruments used must affect the outcome only through the "
            "exposure of interest, not through any other pathway. When a single gene "
            "influences multiple traits — a phenomenon called pleiotropy — this "
            "assumption breaks down and the causal estimate becomes unreliable. "
            "Sensitivity analyses such as MR-Egger and the weighted median estimator "
            "are designed to detect pleiotropy; their presence (and consistency with "
            "the main result) is a mark of a more credible analysis."
        )
    elif paper.study_type == "randomized controlled trial":
        paras.append(
            "RCTs are the gold standard for causal inference, but they are not immune "
            "to limitations. Compliance — whether participants actually adhere to their "
            "assigned condition — is a persistent problem, especially in behavioural "
            "and dietary trials. Short intervention periods may not capture long-term "
            "effects. And the sample enrolled (often volunteers, often younger, often "
            "healthier than average) may not represent the broader population to whom "
            "the results are meant to apply."
        )
    else:
        paras.append(
            "The study design limits the strength of causal claims that can be made. "
            "Without random assignment or a quasi-experimental instrument, confounding "
            "remains a standing concern. Treat the findings as informative but not "
            "definitive, and watch for independent replication."
        )

    # ── Self-report caveat ─────────────────────────────────────────────────
    if re.search(r"self.report|questionnaire|recall|ffq|food frequency", paper.abstract, re.IGNORECASE):
        paras.append(
            "Measurement is another sticking point. Dietary intake and many psychological "
            "variables are self-reported, which introduces recall bias (people misremember "
            "what they ate or did) and social desirability bias (people report what sounds "
            "healthy or acceptable). Food frequency questionnaires in particular are known "
            "to produce systematic under- or over-estimation depending on food type and "
            "respondent characteristics. Objective biomarkers or repeated 24-hour recalls "
            "reduce this problem but are rarely feasible at scale."
        )

    # ── Generalisability caveat ────────────────────────────────────────────
    paras.append(
        "Generalisability is worth considering whenever a study reports striking results. "
        "Findings from one population — defined by age, sex, ethnicity, geographic region, "
        "or baseline health — do not automatically transfer to others. This is especially "
        "relevant in nutrition research, where gut microbiome composition, food environment, "
        "and cultural eating patterns vary enormously across groups."
    )

    # ── Paywall caveat ─────────────────────────────────────────────────────
    if paper.open_access_status == "PAYWALLED":
        paras.append(
            "Note that the full text was behind a paywall during drafting, which means "
            "technical details — the full adjustment model, sensitivity analyses, and "
            "supplementary tables — could not be verified from the abstract alone. "
            "The summary above should be read with that limitation in mind."
        )

    # ── Multiple comparisons note (psychology / non-nutrition) ─────────────
    if not _is_nutrition_paper(paper):
        paras.append(
            "As with most psychological research, it is worth checking whether the "
            "reported effects were pre-registered, and whether the headline finding "
            "survives correction for multiple comparisons. Exploratory findings that "
            "happen to reach p < .05 are a known source of inflated effect sizes in "
            "the psychology literature."
        )

    return "\n\n".join(paras)


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
