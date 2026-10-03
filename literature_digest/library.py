"""Private, audience-scoped literature metadata, independent of mail delivery.

Only papers selected by the research pipeline belong here. The current record
can be enriched by later runs, while each digest keeps its original metadata
and audit location. This module never changes the outbox, sent aliases, or
retrieval checkpoint, and stores neither full text nor application config.
"""
from __future__ import annotations

import json
import unicodedata
from dataclasses import fields
from datetime import datetime, timezone
from os import fspath

from .models import Paper
from .references import reference_files


_PAPER_FIELDS = {field.name for field in fields(Paper)}
_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS library_papers_v1 (
        scope TEXT NOT NULL, paper_id TEXT NOT NULL, metadata TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        last_digest TEXT NOT NULL, audit_path TEXT NOT NULL,
        PRIMARY KEY(scope, paper_id))""",
    """CREATE TABLE IF NOT EXISTS library_aliases_v1 (
        scope TEXT NOT NULL, alias TEXT NOT NULL, paper_id TEXT NOT NULL,
        PRIMARY KEY(scope, alias))""",
    """CREATE INDEX IF NOT EXISTS library_aliases_paper_v1
        ON library_aliases_v1(scope, paper_id)""",
    """CREATE TABLE IF NOT EXISTS library_digest_papers_v1 (
        scope TEXT NOT NULL, digest_id TEXT NOT NULL, paper_key TEXT NOT NULL,
        metadata TEXT NOT NULL, audit_path TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(scope, digest_id, paper_key, audit_path))""",
)


def _ensure_schema(state):
    # Avoid executescript: it implicitly commits any pending caller transaction.
    for statement in _SCHEMA:
        state.db.execute(statement)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _paper(metadata):
    # Index fields, hashes and future export metadata are not dataclass inputs.
    return Paper(**{key: value for key, value in metadata.items() if key in _PAPER_FIELDS})


def _fold(value):
    return unicodedata.normalize("NFC", value.casefold())


def save_papers(state, papers, digest_id, paths):
    """Upsert selected ``Paper`` objects in ``state.scope`` in one transaction.

    ``paths`` is the pipeline's output mapping: ``audit`` for connector bundles
    or ``json`` for ordinary output. Only this audit path is retained. Re-saving
    a digest/paper/audit-path combination cannot overwrite its snapshot. Preview
    and final output can share a digest ID and retain separate associations.
    Aliases join the same paper across sources; titles alone never join papers.
    No network, model, full-text, or delivery operations are performed.
    """
    if not isinstance(digest_id, str) or not digest_id.strip():
        raise ValueError("A non-empty digest ID is required for library records")
    audit_path = fspath(paths.get("audit") or paths.get("json") or "")
    if not isinstance(audit_path, str):
        raise ValueError("The library audit path must be text")
    now = datetime.now(timezone.utc).isoformat()
    with state.db:
        _ensure_schema(state)
        for paper in papers:
            metadata = paper.export(include_text=False)
            aliases = set(paper.aliases)
            # Look up one alias at a time, so a long provenance list cannot hit
            # SQLite's bound-variable limit. This is an indexed point lookup.
            matches = set()
            for alias in aliases:
                row = state.db.execute(
                    "SELECT paper_id FROM library_aliases_v1 WHERE scope=? AND alias=?",
                    (state.scope, alias)).fetchone()
                if row:
                    matches.add(row[0])
            previous = []
            for identifier in matches:
                row = state.db.execute(
                    "SELECT paper_id,metadata,created_at,updated_at FROM library_papers_v1 "
                    "WHERE scope=? AND paper_id=?", (state.scope, identifier)).fetchone()
                if row:
                    previous.append(row)
            # A new identity bridge can join two formerly separate records.
            # Keep the oldest stable index ID and preserve every known alias.
            previous.sort(key=lambda row: (row[2], row[0]))
            identifier = previous[0][0] if previous else paper.key
            created_at = previous[0][2] if previous else now
            old_metadata = [json.loads(row[1]) for row in
                            sorted(previous, key=lambda row: (row[3], row[0]), reverse=True)]
            for old in old_metadata:
                aliases.update(old.get("aliases", []))
                # A source with fewer identifiers must not erase known IDs.
                for field in ("doi", "arxiv_id", "pmcid"):
                    if not metadata.get(field) and old.get(field):
                        metadata[field] = old[field]
            metadata["source_aliases"] = sorted(aliases | set(metadata["source_aliases"]))
            restored = _paper(metadata)
            aliases.update(restored.aliases)
            metadata["key"] = restored.key
            metadata["aliases"] = sorted(aliases)

            # Historical associations use the key selected in that digest,
            # not the mutable library row ID. Identity merges never rewrite
            # or delete these snapshots. Separate preview and final audit paths
            # retain both records, even when they share the daily digest ID.
            snapshot = paper.export(include_text=False)
            snapshot["aliases"] = paper.aliases
            state.db.execute(
                "INSERT OR IGNORE INTO library_digest_papers_v1 VALUES(?,?,?,?,?,?)",
                (state.scope, digest_id, paper.key, _json(snapshot), audit_path, now))
            state.db.execute(
                "INSERT INTO library_papers_v1 VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(scope,paper_id) DO UPDATE SET metadata=excluded.metadata, "
                "updated_at=excluded.updated_at,last_digest=excluded.last_digest, "
                "audit_path=excluded.audit_path",
                (state.scope, identifier, _json(metadata), created_at, now, digest_id, audit_path))
            for old_id, *_ in previous:
                if old_id != identifier:
                    state.db.execute(
                        "UPDATE library_aliases_v1 SET paper_id=? WHERE scope=? AND paper_id=?",
                        (identifier, state.scope, old_id))
                    state.db.execute(
                        "DELETE FROM library_papers_v1 WHERE scope=? AND paper_id=?",
                        (state.scope, old_id))
            for alias in aliases:
                state.db.execute(
                    "INSERT INTO library_aliases_v1 VALUES(?,?,?) "
                    "ON CONFLICT(scope,alias) DO UPDATE SET paper_id=excluded.paper_id",
                    (state.scope, alias, identifier))


def list_papers(state, query=None, limit=50):
    """Return newest saved metadata plus index/audit fields for this audience.

    Search is a literal Unicode case-folded substring of title, authors, or
    abstract, not SQL LIKE or FTS syntax. ``limit=None`` retrieves all matches;
    ordinary listings default to 50 and apply the limit after filtering.
    """
    if query is not None and not isinstance(query, str):
        raise ValueError("Library search must be text")
    if limit is not None and (type(limit) is not int or limit < 0):
        raise ValueError("Library limit must be a non-negative integer or None")
    _ensure_schema(state)
    if limit == 0:
        return []
    needle = _fold(query.strip()) if query else ""
    results = []
    rows = state.db.execute(
        "SELECT paper_id,metadata,created_at,updated_at,last_digest,audit_path "
        "FROM library_papers_v1 WHERE scope=? ORDER BY updated_at DESC,paper_id",
        (state.scope,))
    for identifier, raw, created, updated, digest, audit in rows:
        metadata = json.loads(raw)
        haystacks = [metadata.get("title", ""), metadata.get("abstract", ""),
                     *metadata.get("authors", [])]
        if needle and not any(needle in _fold(value) for value in haystacks):
            continue
        results.append({**metadata, "library_key": identifier, "saved_at": created,
                        "updated_at": updated, "last_digest": digest, "audit_path": audit})
        if limit is not None and len(results) >= limit:
            break
    return results


def export_papers(state, query=None):
    """Return safe ``reference_files`` snapshots (``library.ris``/``.bib``).

    Exports all matching saved records, regardless of sent status or list page
    size. Returns an empty list for an empty selection and writes no files.
    """
    papers = [_paper(metadata) for metadata in list_papers(state, query=query, limit=None)]
    return reference_files(papers, "library")
