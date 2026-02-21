from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional


@dataclass
class CandidatePaper:
    title: str
    authors: str
    journal: str
    publication_date: date
    doi: Optional[str] = None
    abstract: str = ""
    study_type: str = "unknown"
    open_access_status: str = "UNKNOWN"
    source: str = ""
    topic_tags: List[str] = field(default_factory=list)
    link: Optional[str] = None
    extra_links: Dict[str, Optional[str]] = field(
        default_factory=lambda: {
            "publisher": None,
            "pdf": None,
            "pubmed": None,
            "pmc": None,
        }
    )
    peer_reviewed: bool = True
    human_evidence: str = "UNKNOWN"
    score: float = 0.0

    def dedupe_key(self) -> str:
        if self.doi:
            return self.doi.lower().strip()
        return self.title.strip().lower()


@dataclass
class RankedPaper:
    paper: CandidatePaper
    score_breakdown: Dict[str, float]
