from __future__ import annotations

import hashlib
import html
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from urllib.parse import urlsplit

TRACKS = {"bvoc": "生物源挥发性有机物（BVOCs）", "tree_species": "遥感树种识别与分类"}


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def normalize_doi(doi: str | None) -> str:
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", (doi or "").strip(), flags=re.I).lower()


def normalize_arxiv_id(value: str | None) -> str:
    """Return a versionless arXiv identifier, never an arbitrary URL/DOI."""
    text = (value or "").strip()
    text = re.sub(r"^(?:arxiv:\s*|10\.48550/arxiv\.)", "", text, flags=re.I)
    if text.lower().startswith(("https://", "http://")):
        parts = urlsplit(text)
        if parts.hostname not in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
            return ""
        text = re.sub(r"^/(?:abs|pdf)/", "", parts.path)
    text = re.sub(r"\.pdf$", "", text, flags=re.I)
    text = re.sub(r"v[1-9]\d*$", "", text, flags=re.I)
    # Both current and pre-2007 identifiers are supported.
    if re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-z][a-z0-9.-]*(?:\.[a-z]{2})?/\d{7})", text, re.I):
        return text.lower()
    return ""


def normalize_pmcid(value: str | None) -> str:
    value = (value or "").strip().upper()
    return value if re.fullmatch(r"PMC[0-9]+", value) else ""


@dataclass
class Paper:
    title: str
    source_id: str
    source: str
    url: str
    doi: str = ""
    abstract: str = ""
    authors: list[str] = field(default_factory=list)
    journal: str = ""
    publication_date: str = ""
    publication_date_label: str = ""
    index_date: str = ""
    kind: str = "发表类型未确定；同行评审状态未经核实"
    pmcid: str = ""
    open_access: bool = False
    full_text: str = ""
    full_text_url: str = ""
    evidence_level: str = "仅元数据"
    tracks: list[str] = field(default_factory=list)
    source_aliases: list[str] = field(default_factory=list)
    provenance: list[dict] = field(default_factory=list)
    analysis: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    arxiv_id: str = ""
    # Relationships are descriptive, not identity aliases (except is-identical-to).
    relations: list[dict] = field(default_factory=list)
    figures: list[dict] = field(default_factory=list)

    @property
    def key(self) -> str:
        if normalize_doi(self.doi):
            return "doi:" + normalize_doi(self.doi)
        arxiv = normalize_arxiv_id(self.arxiv_id or (self.source_id if self.source.lower() == "arxiv" else ""))
        if arxiv:
            return "arxiv:" + arxiv
        return self.source.lower() + ":" + self.source_id

    @property
    def aliases(self) -> list[str]:
        aliases = [self.key, self.source.lower() + ":" + self.source_id] + self.source_aliases
        if normalize_pmcid(self.pmcid):
            aliases.append("pmc:" + normalize_pmcid(self.pmcid))
        for value in (self.arxiv_id, self.source_id if self.source.lower() == "arxiv" else "", normalize_doi(self.doi)):
            arxiv = normalize_arxiv_id(value)
            if arxiv:
                aliases.append("arxiv:" + arxiv)
        normalized = []
        for alias in aliases:
            if alias.lower().startswith("doi:"):
                alias = "doi:" + normalize_doi(alias[4:])
            elif alias.lower().startswith("arxiv:"):
                base = normalize_arxiv_id(alias[6:])
                if base:
                    alias = "arxiv:" + base
            normalized.append(alias)
        return sorted(set(normalized))

    @property
    def evidence(self) -> str:
        return self.full_text or self.abstract

    def export(self, include_text: bool = False) -> dict:
        result = asdict(self)
        result["key"] = self.key
        result["evidence_sha256"] = hashlib.sha256(self.evidence.encode()).hexdigest()
        if not include_text:
            result.pop("full_text", None)
        return result


def parse_date_parts(value: dict) -> str:
    if not isinstance(value, dict):
        return ""
    values = value.get("date-parts", [])
    if not isinstance(values, list) or not values or not isinstance(values[0], list):
        return ""
    parts = values[0]
    if not 1 <= len(parts) <= 3 or any(isinstance(part, (bool, float)) for part in parts):
        return ""
    # Retain actual granularity: never invent January 1 for an unknown day.
    try:
        year = int(parts[0])
        if len(parts) >= 3:
            return date(year, int(parts[1]), int(parts[2])).isoformat()
        if len(parts) == 2:
            date(year, int(parts[1]), 1)
            return f"{year:04d}-{int(parts[1]):02d}"
        date(year, 1, 1)
        return f"{year:04d}"
    except (ValueError, TypeError):
        return ""
