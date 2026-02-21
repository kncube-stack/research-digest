from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence, Set

from .config import AppConfig
from .models import CandidatePaper
from .utils import (
    http_get,
    http_get_json,
    normalize_doi,
    parse_date_parts,
    parse_pub_date,
    safe_sleep,
    strip_html,
    within_window,
)

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
PREPRINT_HINTS = ("biorxiv", "medrxiv", "arxiv", "ssrn", "research square")
HUMAN_HINTS = (
    "participants",
    "patients",
    "male participants",
    "female participants",
    "men and boys",
    "adolescents",
    "children",
    "adults",
    "pregnant",
    "newborn",
    "postmenopausal",
    "clinical trial",
    "randomized trial",
    "cohort",
    "cross-sectional",
    "longitudinal",
    "survey",
    "uk biobank",
    "genome-wide association",
    "gwas",
    "mendelian randomization",
    "mendelian randomisation",
)
NON_HUMAN_HINTS = (
    "mouse",
    "mice",
    "murine",
    "rat",
    "rats",
    "zebrafish",
    "drosophila",
    "c. elegans",
    "canine",
    "porcine",
    "ovine",
    "nonhuman primate",
    "animal model",
    "rodent",
    "veterinary",
    "livestock",
    "plant",
    "cotton",
    "crop",
    "maize",
    "wheat",
)
IN_VITRO_HINTS = (
    "in vitro",
    "cell line",
    "organoid",
    "fibroblast",
    "neuronal culture",
    "primary culture",
    "ex vivo",
    "tissue section",
)
NON_CLINICAL_DOMAIN_HINTS = (
    "battery",
    "microstrip",
    "antenna",
    "x-band",
    "image classification",
    "federated learning",
    "wgan",
    "pinn",
    "thermal management system",
    "electric vehicles",
    "signal processing",
)


class SourceFetcher:
    def __init__(self, config: AppConfig):
        self.config = config

    def fetch_all(self, now: Optional[date] = None) -> List[CandidatePaper]:
        if now is None:
            now = date.today()
        start = now - timedelta(days=max(self.config.TIME_WINDOW_DAYS - 1, 0))
        papers: List[CandidatePaper] = []

        papers.extend(self.fetch_crossref(start, now))
        papers.extend(self.fetch_pubmed(start, now))
        papers.extend(self.fetch_rss(start, now))

        papers = self._dedupe_candidates(papers)
        self.enrich_missing_metadata_from_crossref(papers, start, now)
        self.resolve_open_access(papers)
        return papers

    def fetch_crossref(self, start: date, end: date) -> List[CandidatePaper]:
        out: List[CandidatePaper] = []
        base_url = "https://api.crossref.org/works"

        for topic in self.config.TOPICS:
            params = {
                "filter": (
                    f"from-pub-date:{start.isoformat()},"
                    f"until-pub-date:{end.isoformat()},"
                    "type:journal-article"
                ),
                "rows": 80,
                "sort": "published",
                "order": "desc",
                "query.bibliographic": topic,
            }
            try:
                payload = http_get_json(base_url, params=params)
            except Exception:
                continue

            for item in payload.get("message", {}).get("items", []):
                paper = self._candidate_from_crossref_item(item, topic)
                if not paper:
                    continue
                if not within_window(paper.publication_date, end, self.config.TIME_WINDOW_DAYS):
                    continue
                out.append(paper)

            safe_sleep(0.15)

        return self._dedupe_candidates(out)

    def _candidate_from_crossref_item(
        self, item: Dict[str, object], topic: str
    ) -> Optional[CandidatePaper]:
        paper_type = str(item.get("type", "")).lower()
        if paper_type != "journal-article":
            return None

        title = ""
        title_list = item.get("title")
        if isinstance(title_list, list) and title_list:
            title = strip_html(str(title_list[0]))
        if not title:
            return None

        journal = ""
        container = item.get("container-title")
        if isinstance(container, list) and container:
            journal = str(container[0]).strip()

        if self._looks_like_preprint(title, journal):
            return None

        pub_date = self._crossref_publication_date(item)
        if not pub_date:
            return None

        doi = normalize_doi(str(item.get("DOI", "")))
        abstract = strip_html(str(item.get("abstract", "")))

        authors = "Unknown"
        author_list = item.get("author")
        if isinstance(author_list, list) and author_list:
            first = author_list[0]
            if isinstance(first, dict):
                family = str(first.get("family", "")).strip()
                given = str(first.get("given", "")).strip()
                if family or given:
                    first_name = (given + " " + family).strip()
                    authors = f"{first_name} et al." if len(author_list) > 1 else first_name

        links = {
            "publisher": str(item.get("URL", "")) or None,
            "pdf": None,
            "pubmed": None,
            "pmc": None,
        }

        link_entries = item.get("link")
        if isinstance(link_entries, list):
            for entry in link_entries:
                if not isinstance(entry, dict):
                    continue
                content_type = str(entry.get("content-type", "")).lower()
                entry_url = str(entry.get("URL", "")) or None
                if entry_url and content_type == "application/pdf":
                    links["pdf"] = entry_url
                    break

        oa_status = "UNKNOWN"
        licenses = item.get("license")
        if isinstance(licenses, list) and licenses:
            oa_status = "OPEN_ACCESS"
        human_evidence = self._infer_human_evidence_from_text(title, abstract, journal)

        paper = CandidatePaper(
            title=title,
            authors=authors,
            journal=journal,
            publication_date=pub_date,
            doi=doi,
            abstract=abstract,
            source="crossref",
            open_access_status=oa_status,
            link=links["publisher"],
            extra_links=links,
            topic_tags=[topic],
            peer_reviewed=True,
            human_evidence=human_evidence,
        )
        return paper

    def _crossref_publication_date(self, item: Dict[str, object]) -> Optional[date]:
        for key in ("published-online", "published-print", "issued", "created"):
            field = item.get(key)
            if not isinstance(field, dict):
                continue
            date_parts = field.get("date-parts")
            if isinstance(date_parts, list) and date_parts:
                first = date_parts[0]
                if isinstance(first, list):
                    parsed = parse_date_parts(first)
                    if parsed:
                        return parsed
        return None

    def fetch_pubmed(self, start: date, end: date) -> List[CandidatePaper]:
        ids: Set[str] = set()
        esearch = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        for topic in self.config.TOPICS:
            term = f'({topic}) AND ("{start:%Y/%m/%d}"[Date - Publication] : "{end:%Y/%m/%d}"[Date - Publication])'
            params = {
                "db": "pubmed",
                "retmode": "json",
                "retmax": 60,
                "term": term,
                "tool": self.config.PUBMED_TOOL,
            }
            if self.config.PUBMED_EMAIL:
                params["email"] = self.config.PUBMED_EMAIL
            try:
                payload = http_get_json(esearch, params=params)
            except Exception:
                continue
            for pmid in payload.get("esearchresult", {}).get("idlist", []):
                ids.add(str(pmid))
            safe_sleep(0.2)

        if not ids:
            return []

        papers: List[CandidatePaper] = []
        id_list = sorted(ids)
        efetch = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

        for i in range(0, len(id_list), 120):
            chunk = id_list[i : i + 120]
            params = {
                "db": "pubmed",
                "retmode": "xml",
                "id": ",".join(chunk),
                "tool": self.config.PUBMED_TOOL,
            }
            if self.config.PUBMED_EMAIL:
                params["email"] = self.config.PUBMED_EMAIL
            try:
                xml_data = http_get(efetch, params=params)
            except Exception:
                continue

            try:
                root = ET.fromstring(xml_data)
            except ET.ParseError:
                continue

            for article in root.findall(".//PubmedArticle"):
                paper = self._candidate_from_pubmed_article(article)
                if not paper:
                    continue
                if not within_window(paper.publication_date, end, self.config.TIME_WINDOW_DAYS):
                    continue
                papers.append(paper)

            safe_sleep(0.2)

        return self._dedupe_candidates(papers)

    def _candidate_from_pubmed_article(self, article: ET.Element) -> Optional[CandidatePaper]:
        title = " ".join(article.findtext(".//ArticleTitle", default="").split())
        if not title:
            return None

        journal = " ".join(article.findtext(".//Journal/Title", default="").split())
        if self._looks_like_preprint(title, journal):
            return None

        pub_types = [
            (pt.text or "").strip().lower()
            for pt in article.findall(".//PublicationTypeList/PublicationType")
        ]
        if any("preprint" in pt for pt in pub_types):
            return None

        pub_date = self._pubmed_publication_date(article)
        if not pub_date:
            return None

        parts: List[str] = []
        for abs_node in article.findall(".//Abstract/AbstractText"):
            section = "".join(abs_node.itertext()).strip()
            if section:
                parts.append(section)
        abstract = " ".join(parts)
        human_evidence = self._pubmed_human_evidence(article, title, abstract, pub_types)

        doi = None
        pmid = ""
        pmc = None
        for id_node in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
            id_type = (id_node.attrib.get("IdType") or "").lower()
            value = (id_node.text or "").strip()
            if id_type == "doi":
                doi = normalize_doi(value)
            elif id_type == "pubmed":
                pmid = value
            elif id_type == "pmc":
                pmc = value

        authors = "Unknown"
        author_nodes = article.findall(".//AuthorList/Author")
        if author_nodes:
            first = author_nodes[0]
            family = (first.findtext("LastName") or "").strip()
            given = (first.findtext("ForeName") or "").strip()
            if family or given:
                first_author = (given + " " + family).strip()
                authors = f"{first_author} et al." if len(author_nodes) > 1 else first_author

        pubmed_link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None
        pmc_link = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmc}/" if pmc else None

        links = {
            "publisher": f"https://doi.org/{doi}" if doi else None,
            "pdf": None,
            "pubmed": pubmed_link,
            "pmc": pmc_link,
        }

        status = "OPEN_ACCESS" if pmc else "UNKNOWN"
        paper = CandidatePaper(
            title=title,
            authors=authors,
            journal=journal,
            publication_date=pub_date,
            doi=doi,
            abstract=abstract,
            source="pubmed",
            open_access_status=status,
            link=pubmed_link or links["publisher"],
            extra_links=links,
            peer_reviewed=True,
            human_evidence=human_evidence,
        )
        return paper

    def _pubmed_publication_date(self, article: ET.Element) -> Optional[date]:
        # Prefer explicit online date when present.
        article_date = article.find(".//ArticleDate")
        if article_date is not None:
            parsed = self._pubmed_date_node(article_date)
            if parsed:
                return parsed

        pub_date = article.find(".//JournalIssue/PubDate")
        if pub_date is not None:
            parsed = self._pubmed_date_node(pub_date)
            if parsed:
                return parsed

        return None

    def _pubmed_date_node(self, node: ET.Element) -> Optional[date]:
        year_txt = (node.findtext("Year") or "").strip()
        if not year_txt.isdigit():
            medline = (node.findtext("MedlineDate") or "").strip()
            if medline:
                m = re.search(r"(19|20)\d{2}", medline)
                if m:
                    return date(int(m.group(0)), 1, 1)
            return None

        year = int(year_txt)
        month_txt = (node.findtext("Month") or "1").strip()
        day_txt = (node.findtext("Day") or "1").strip()

        month_map = {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "sept": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }

        if month_txt.isdigit():
            month = int(month_txt)
        else:
            month = month_map.get(month_txt[:3].lower(), 1)

        day = int(day_txt) if day_txt.isdigit() else 1
        try:
            return date(year, month, day)
        except ValueError:
            return None

    def fetch_rss(self, start: date, end: date) -> List[CandidatePaper]:
        papers: List[CandidatePaper] = []
        for feed in self.config.RSS_FEEDS:
            name = feed.get("name", "Unknown Journal")
            url = feed.get("url", "")
            if not url:
                continue
            try:
                xml_data = http_get(url)
                root = ET.fromstring(xml_data)
            except Exception:
                continue

            items = root.findall(".//item")
            atom_entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")
            if atom_entries:
                items.extend(atom_entries)

            for item in items:
                paper = self._candidate_from_feed_item(item, name)
                if not paper:
                    continue
                if not within_window(paper.publication_date, end, self.config.TIME_WINDOW_DAYS):
                    continue
                papers.append(paper)

            safe_sleep(0.1)

        return self._dedupe_candidates(papers)

    def _candidate_from_feed_item(self, item: ET.Element, journal_name: str) -> Optional[CandidatePaper]:
        title = item.findtext("title") or item.findtext("{http://www.w3.org/2005/Atom}title")
        if not title:
            return None
        title = strip_html(title)

        link = item.findtext("link")
        if not link:
            link_node = item.find("{http://www.w3.org/2005/Atom}link")
            if link_node is not None:
                link = link_node.attrib.get("href")
        link = (link or "").strip() or None

        pub_text = (
            item.findtext("pubDate")
            or item.findtext("published")
            or item.findtext("updated")
            or item.findtext("{http://www.w3.org/2005/Atom}published")
            or item.findtext("{http://www.w3.org/2005/Atom}updated")
        )
        if not pub_text:
            return None
        pub_date = parse_pub_date(pub_text)
        if not pub_date:
            return None

        summary = (
            item.findtext("description")
            or item.findtext("summary")
            or item.findtext("{http://www.w3.org/2005/Atom}summary")
            or ""
        )
        summary = strip_html(summary)

        author = (
            item.findtext("creator")
            or item.findtext("author")
            or item.findtext("{http://purl.org/dc/elements/1.1/}creator")
            or item.findtext("{http://www.w3.org/2005/Atom}author")
            or "Unknown"
        )

        doi = None
        if link:
            m = DOI_RE.search(link)
            if m:
                doi = normalize_doi(m.group(0))
        if not doi:
            m = DOI_RE.search(summary)
            if m:
                doi = normalize_doi(m.group(0))

        if self._looks_like_preprint(title, journal_name):
            return None

        links = {
            "publisher": link,
            "pdf": None,
            "pubmed": None,
            "pmc": None,
        }
        human_evidence = self._infer_human_evidence_from_text(title, summary, journal_name)

        paper = CandidatePaper(
            title=title,
            authors=author,
            journal=journal_name,
            publication_date=pub_date,
            doi=doi,
            abstract=summary,
            source="rss",
            link=link,
            extra_links=links,
            peer_reviewed=True,
            human_evidence=human_evidence,
        )
        return paper

    def enrich_missing_metadata_from_crossref(
        self, papers: Sequence[CandidatePaper], start: date, end: date
    ) -> None:
        base_url = "https://api.crossref.org/works"
        for paper in papers:
            if paper.doi and paper.journal and paper.abstract:
                continue
            params = {
                "query.title": paper.title,
                "rows": 1,
                "sort": "score",
                "order": "desc",
            }
            try:
                payload = http_get_json(base_url, params=params)
            except Exception:
                continue

            items = payload.get("message", {}).get("items", [])
            if not items:
                continue

            item = items[0]
            enriched = self._candidate_from_crossref_item(item, topic="")
            if not enriched:
                continue
            if not (start <= enriched.publication_date <= end):
                continue

            # Lightweight title overlap check to avoid bad matches.
            if self._title_overlap_ratio(paper.title, enriched.title) < 0.45:
                continue

            paper.doi = paper.doi or enriched.doi
            paper.journal = paper.journal or enriched.journal
            if not paper.abstract:
                paper.abstract = enriched.abstract
            if not paper.extra_links.get("publisher") and enriched.extra_links.get("publisher"):
                paper.extra_links["publisher"] = enriched.extra_links["publisher"]
                paper.link = paper.link or enriched.extra_links["publisher"]
            if not paper.extra_links.get("pdf") and enriched.extra_links.get("pdf"):
                paper.extra_links["pdf"] = enriched.extra_links["pdf"]
            if paper.open_access_status == "UNKNOWN" and enriched.open_access_status != "UNKNOWN":
                paper.open_access_status = enriched.open_access_status
            if paper.human_evidence == "UNKNOWN" and enriched.human_evidence != "UNKNOWN":
                paper.human_evidence = enriched.human_evidence
            elif paper.human_evidence == "UNKNOWN":
                paper.human_evidence = self._infer_human_evidence_from_text(
                    paper.title, paper.abstract, paper.journal
                )

            safe_sleep(0.1)

    def resolve_open_access(self, papers: Sequence[CandidatePaper]) -> None:
        email = self.config.UNPAYWALL_EMAIL.strip()
        for paper in papers:
            if paper.open_access_status == "OPEN_ACCESS":
                continue
            if paper.extra_links.get("pmc"):
                paper.open_access_status = "OPEN_ACCESS"
                continue
            if not paper.doi:
                continue
            if not email:
                # Fallback heuristic when no Unpaywall email is configured.
                if paper.extra_links.get("pdf"):
                    paper.open_access_status = "OPEN_ACCESS"
                elif paper.open_access_status == "UNKNOWN":
                    paper.open_access_status = "UNKNOWN"
                continue

            url = f"https://api.unpaywall.org/v2/{paper.doi}"
            try:
                payload = http_get_json(url, params={"email": email}, timeout=20)
            except Exception:
                continue

            is_oa = bool(payload.get("is_oa"))
            best = payload.get("best_oa_location") or {}
            if is_oa:
                paper.open_access_status = "OPEN_ACCESS"
                if isinstance(best, dict):
                    pdf = best.get("url_for_pdf") or best.get("url")
                    if pdf and not paper.extra_links.get("pdf"):
                        paper.extra_links["pdf"] = str(pdf)
                    if best.get("url") and not paper.extra_links.get("publisher"):
                        paper.extra_links["publisher"] = str(best.get("url"))
            else:
                paper.open_access_status = "PAYWALLED"

            safe_sleep(0.12)

    def _pubmed_human_evidence(
        self, article: ET.Element, title: str, abstract: str, pub_types: Sequence[str]
    ) -> str:
        mesh_terms = [
            (node.text or "").strip().lower()
            for node in article.findall(".//MeshHeadingList/MeshHeading/DescriptorName")
        ]

        has_humans = "humans" in mesh_terms
        has_animals = "animals" in mesh_terms

        if has_humans:
            return "HUMAN"
        if has_animals:
            return "NON_HUMAN"

        if any("animal experimentation" in pt for pt in pub_types):
            return "NON_HUMAN"

        return self._infer_human_evidence_from_text(title, abstract, "")

    def _infer_human_evidence_from_text(self, title: str, abstract: str, journal: str) -> str:
        text = f"{title} {abstract} {journal}".lower()

        has_non_clinical_domain = any(hint in text for hint in NON_CLINICAL_DOMAIN_HINTS)
        has_non_human = any(hint in text for hint in NON_HUMAN_HINTS) or any(
            hint in text for hint in IN_VITRO_HINTS
        )
        has_human_terms = " human " in f" {text} " or " humans " in f" {text} "
        has_human_study_signals = any(hint in text for hint in HUMAN_HINTS) or bool(
            re.search(
                r"\b(participants?|patients?|adults?|children|adolescents?|students?|cohort|trial|survey|case-control|longitudinal)\b",
                text,
            )
        )

        if has_non_human and not has_human_study_signals:
            return "NON_HUMAN"
        if has_non_clinical_domain and not has_human_study_signals:
            return "UNKNOWN"
        if has_human_study_signals:
            return "HUMAN"
        if has_human_terms:
            return "UNKNOWN"
        if has_non_human:
            return "NON_HUMAN"
        return "UNKNOWN"

    def _dedupe_candidates(self, papers: Sequence[CandidatePaper]) -> List[CandidatePaper]:
        out: List[CandidatePaper] = []
        seen = set()
        for paper in papers:
            key = paper.dedupe_key()
            if key in seen:
                continue
            seen.add(key)
            out.append(paper)
        return out

    def _looks_like_preprint(self, title: str, journal: str) -> bool:
        text = f"{title} {journal}".lower()
        return any(hint in text for hint in PREPRINT_HINTS)

    def _title_overlap_ratio(self, a: str, b: str) -> float:
        words_a = {w for w in re.findall(r"[a-z0-9]+", a.lower()) if len(w) > 2}
        words_b = {w for w in re.findall(r"[a-z0-9]+", b.lower()) if len(w) > 2}
        if not words_a or not words_b:
            return 0.0
        inter = len(words_a & words_b)
        union = len(words_a | words_b)
        return inter / union if union else 0.0
