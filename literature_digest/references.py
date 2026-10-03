"""Conservative UTF-8 citation exports for the papers actually in one issue.

No identifiers or missing metadata are synthesized. Structured source names are
used when available; unstructured names stay literal rather than guessing a
surname (especially important for organizations and non-Western name order).
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date
from urllib.parse import urlsplit

from .analysis import unique_papers
from .models import normalize_doi

EXPORT_VERSION = 1
FORMATS = {"ris": "application/x-research-info-systems", "bib": "application/x-bibtex"}
SYNTHETIC_NOTE = "DEMO / SYNTHETIC: invented offline fixture; not a real publication."


def _flat(value):
    if not isinstance(value, str):
        return ""
    # Never let metadata add another RIS tag, BibTeX line, or control sequence.
    value = "".join(" " if unicodedata.category(c) in {"Cc", "Zl", "Zp"} else c for c in value)
    return " ".join(value.split())


def _doi(value):
    value = normalize_doi(value) if isinstance(value, str) else ""
    return value if re.fullmatch(r'10\.\d{4,9}/[^\s<>"\x00-\x1f\x7f]+', value) else ""


def _url(value):
    if not isinstance(value, str) or value != _flat(value) or any(c.isspace() for c in value):
        return ""
    try:
        parts = urlsplit(value)
        return value if parts.scheme in {"http", "https"} and parts.hostname and not parts.username and not parts.password else ""
    except ValueError:
        return ""


def _date(value):
    value = _flat(value)
    if not re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", value):
        return ""
    try:
        values = [int(v) for v in value.split("-")]
        date(*(values + [1] * (3 - len(values))))
    except ValueError:
        return ""
    return value


def _synthetic(paper):
    return paper.source == "demo" or any(p.get("synthetic") for p in paper.provenance)


def _preprint(paper):
    return (paper.source.lower() == "arxiv" or "预印本" in paper.kind
            or "preprint" in paper.kind.lower()
            or any(p.get("type") == "posted-content" for p in paper.provenance))


def _authors(paper):
    details = paper.author_details
    # Alignment is important: do not apply another provider's parsing to a name.
    for index, name in enumerate(paper.authors):
        detail = details[index] if index < len(details) and isinstance(details[index], dict) else {}
        family, given = _flat(detail.get("family")), _flat(detail.get("given"))
        literal = _flat(detail.get("literal"))
        if family:
            yield {"family": family, "given": given, "literal": ""}
        elif literal or _flat(name):
            yield {"family": "", "given": "", "literal": literal or _flat(name)}


def _note(paper):
    values = [SYNTHETIC_NOTE] if _synthetic(paper) else []
    if _flat(paper.kind):
        values.append(_flat(paper.kind))
    if _flat(paper.publication_date_label):
        values.append("Date source: " + _flat(paper.publication_date_label))
    return "; ".join(values)


def ris(papers):
    """One independently terminated RIS record per global reference, UTF-8."""
    records = []
    for paper in unique_papers(papers):
        kind = "GEN" if _synthetic(paper) else "UNPB" if _preprint(paper) else "JOUR" if paper.journal else "GEN"
        fields = [("TY", kind), ("TI", paper.title)]
        for author in _authors(paper):
            name = author["literal"] or author["family"] + (", " + author["given"] if author["given"] else "")
            fields.append(("AU", name))
        publication = _date(paper.publication_date)
        fields += [("JO", paper.journal), ("PY", publication[:4]), ("DA", publication.replace("-", "/")),
                   ("DO", _doi(paper.doi)), ("UR", _url(paper.url)), ("AB", paper.abstract), ("N1", _note(paper))]
        if paper.arxiv_id:
            fields.append(("AN", "arXiv:" + _flat(paper.arxiv_id)))
        fields.extend(("KW", track) for track in paper.tracks)
        records.append("\n".join(f"{tag}  - {_flat(value)}" for tag, value in fields if _flat(value)) + "\nER  - \n")
    return "\n".join(records)


_BIB_ESCAPES = {"\\": r"\textbackslash{}", "{": r"\textbraceleft{}", "}": r"\textbraceright{}", "$": r"\$", "&": r"\&",
                "#": r"\#", "%": r"\%", "_": r"\_", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def _bib(value):
    return "".join(_BIB_ESCAPES.get(char, char) for char in _flat(value))


def bibtex(papers):
    """Brace-safe Unicode BibTeX. Stable ASCII keys never include source text."""
    records = []
    for paper in unique_papers(papers):
        kind = "article" if paper.journal and not (_synthetic(paper) or _preprint(paper)) else "misc"
        key = "paper_" + hashlib.sha256(paper.key.encode("utf-8")).hexdigest()[:20]
        fields = [("title", _bib(paper.title))]
        authors = []
        for author in _authors(paper):
            if author["literal"]:
                authors.append("{" + _bib(author["literal"]) + "}")
            else:
                # Protect family/given groups against embedded 'and' or commas.
                authors.append("{" + _bib(author["family"]) + "}" +
                               (", {" + _bib(author["given"]) + "}" if author["given"] else ""))
        fields.append(("author", " and ".join(authors)))
        publication = _date(paper.publication_date)
        fields += [("journal", _bib(paper.journal)), ("year", publication[:4]), ("date", publication),
                   ("doi", _bib(_doi(paper.doi))), ("url", _bib(_url(paper.url))),
                   ("abstract", _bib(paper.abstract)), ("note", _bib(_note(paper)))]
        if paper.arxiv_id:
            fields += [("eprint", _bib(paper.arxiv_id)), ("archivePrefix", "arXiv")]
        fields.append(("keywords", _bib(", ".join(paper.tracks))))
        body = ",\n".join("  " + field + " = {" + value + "}" for field, value in fields if value)
        records.append("@" + kind + "{" + key + ",\n" + body + "\n}\n")
    return "\n".join(records)


def reference_files(papers, stem):
    """Create an immutable JSON-serializable attachment snapshot; empty means none."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", stem):
        raise ValueError("Unsafe citation export filename")
    papers = unique_papers(papers)
    if not papers:
        return []
    files = []
    for extension, content in (("ris", ris(papers)), ("bib", bibtex(papers))):
        files.append({"filename": stem + "." + extension, "format": extension,
                      "content_type": FORMATS[extension], "content": content,
                      "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                      "paper_count": len(papers), "synthetic": any(_synthetic(p) for p in papers)})
    return files


def reference_manifest(files):
    return [{key: value for key, value in item.items() if key != "content"} for item in files]


def validate_reference_files(files):
    """Fail before SMTP if an outbox attachment or its metadata was corrupted."""
    if not isinstance(files, list) or len(files) not in (0, 2):
        raise ValueError("Invalid prepared citation attachments")
    seen = set()
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("Invalid prepared citation attachment")
        extension = item.get("format")
        if not isinstance(extension, str) or extension not in FORMATS or extension in seen:
            raise ValueError("Invalid prepared citation attachment format")
        seen.add(extension)
        if (not isinstance(item.get("filename"), str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\." + extension, item["filename"])
                or item.get("content_type") != FORMATS[extension]
                or not isinstance(item.get("content"), str)
                or not item["content"]
                or item.get("sha256") != hashlib.sha256(item["content"].encode("utf-8")).hexdigest()):
            raise ValueError("Prepared citation attachment failed integrity validation")
    return files
