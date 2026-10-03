"""Validate agent-written closing synthesis and explicitly proposed research ideas.

The program checks evidence provenance and structure, never invents ideas or
claims that an untested hypothesis has been established by its source papers.
"""
from __future__ import annotations

import re

from .analysis import _check_text, reference_map, unique_papers, validate_overview


OUTLOOK_POLICY = "agent-research-outlook-v1"
IDEA_FIELDS = ("hypothesis", "experiment", "validation", "expected_value")


def empty_outlook():
    return {"synthesis": {"paragraphs": []}, "open_questions": [], "ideas": []}


def _sentences(items, papers, language, label, maximum=4):
    if not isinstance(items, list) or not 1 <= len(items) <= maximum:
        raise ValueError(label + " requires one to " + str(maximum) + " cited statements")
    return validate_overview({"paragraphs": [{"sentences": items}]}, papers, language)[0]["sentences"]


def _proposal_text(value, language, limit):
    value = _check_text(value, language, limit)
    if re.search(r"\[\d+(?:[\s,–-]+\d+)*\]|<\s*sup\b", value, re.I):
        raise ValueError("Research idea citations belong in structured basis statements")
    return value


def validate_outlook(data, papers, language="zh-CN"):
    """Return normalized, source-checked outlook content without adding findings.

Source anchors apply to synthesis, open-question motivation and each idea's
basis. The hypothesis, planned experiment, validation and expected value are
agent proposals, not quotations or established findings. Entailment, usefulness
and global novelty still require scientific review.
"""
    if not isinstance(data, dict) or set(data) != {"synthesis", "open_questions", "ideas"}:
        raise ValueError("Outlook requires synthesis, open_questions and ideas")
    papers = unique_papers(papers)
    if not papers:
        if data != empty_outlook():
            raise ValueError("Empty selections require an empty outlook")
        return empty_outlook()
    synthesis = validate_overview(data["synthesis"], papers, language)
    refs = {citation["ref"] for paragraph in synthesis for sentence in paragraph["sentences"]
            for citation in sentence["citations"]}
    if len(papers) > 1 and len(refs) < 2:
        raise ValueError("A multi-paper closing synthesis must cite at least two selected papers")
    questions = _sentences(data["open_questions"], papers, language, "Open questions")
    ideas = data["ideas"]
    if not isinstance(ideas, list) or not 1 <= len(ideas) <= 4:
        raise ValueError("Outlook requires one to four proposed research ideas")
    checked, titles = [], set()
    for idea in ideas:
        if not isinstance(idea, dict) or set(idea) != {"status", "title", "basis", *IDEA_FIELDS}:
            raise ValueError("Research idea requires status, title, cited basis and all four proposal fields")
        if idea["status"] != "proposed":
            raise ValueError("Research ideas must be marked proposed, not established findings")
        title = _proposal_text(idea["title"], language, 180)
        if title.casefold() in titles:
            raise ValueError("Research idea titles must be distinct")
        titles.add(title.casefold())
        basis = _sentences(idea["basis"], papers, language, "Research idea basis", 3)
        item = {"status": "proposed", "title": title, "basis": basis}
        for field in IDEA_FIELDS:
            item[field] = _proposal_text(idea[field], language, 2400 if field == "experiment" else 1600)
        checked.append(item)
    return {"synthesis": {"paragraphs": synthesis}, "open_questions": questions, "ideas": checked}


def prepare_outlook(data, papers, language="zh-CN"):
    """Bind validated content to this issue's ordered bibliography."""
    return {**validate_outlook(data, papers, language), "policy": OUTLOOK_POLICY,
            "references": reference_map(papers), "language": language}


def checked_outlook(data, papers, language="zh-CN", allow_synthetic=False):
    """Rendering fails closed on absent, stale or tampered closing content."""
    if data is None:
        return None
    if not allow_synthetic and any((paper.analysis or {}).get("mode") == "synthetic_demo" for paper in papers):
        return None
    try:
        if (not isinstance(data, dict) or data.get("policy") != OUTLOOK_POLICY
                or data.get("references") != reference_map(papers) or data.get("language") != language):
            return None
        return validate_outlook({key: data[key] for key in ("synthesis", "open_questions", "ideas")}, papers, language)
    except (ValueError, TypeError, KeyError):
        return None
