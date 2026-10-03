"""Source-anchored design interpretation, limitations and per-paper implications."""
from __future__ import annotations

from .analysis import _check_anchor, _check_text


PERSPECTIVE_FIELDS = ("design_logic", "limitations", "inspiration")


def validate_perspective(data, evidence, language="zh-CN"):
    if not isinstance(data, dict) or set(data) != set(PERSPECTIVE_FIELDS):
        raise ValueError("Paper perspective requires design_logic, limitations and inspiration")
    checked = {}
    for field in PERSPECTIVE_FIELDS:
        items = data[field]
        if not isinstance(items, list) or not 1 <= len(items) <= 3:
            raise ValueError("Each paper perspective field requires one to three anchored statements")
        checked[field] = []
        for item in items:
            if not isinstance(item, dict) or set(item) != {"text", "evidence", "kind"}:
                raise ValueError("Paper perspective statements require text, evidence and kind")
            if item["kind"] not in ("reported", "inferred"):
                raise ValueError("Paper perspective kind must be reported or inferred")
            checked[field].append({"text": _check_text(item["text"], language),
                                   "evidence": _check_anchor(item["evidence"], evidence),
                                   "kind": item["kind"]})
    return checked


def checked_perspective(paper, language, allow_synthetic=False):
    try:
        modes = ("llm_grounded", "synthetic_demo") if allow_synthetic else ("llm_grounded",)
        if (paper.analysis or {}).get("mode") not in modes:
            return None
        return validate_perspective(paper.analysis["perspective"], paper.evidence, language)
    except (ValueError, TypeError, KeyError):
        return None
