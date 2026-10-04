"""Explicit recovery of a completed, never-claimed connector preparation.

This is not a sent revision, a claim reset, or permission to send. Old artifacts
remain immutable; only the original lifecycle status and successor link change.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
import tempfile

from .agent_jobs import (_json, _load, _paper, _public, _refresh_result, _registered_figures,
                         _sha, is_agent)
from .connector_delivery import _check_payload, _text, read_json
from .pipeline import atomic_write
from .relevance import merge_papers
from .state import State, state_scope


def _verified_evidence(state, config, job, audit):
    """Replay immutable snapshots in ingest order, not unchecked candidate rows."""
    if job["events"] != audit.get("agent_tool_events"):
        raise ValueError("Source job events failed prepared audit integrity validation")
    rows = state.db.execute(
        "SELECT sha256,path,ingested FROM agent_sources_v1 WHERE scope=? AND job_id=?",
        (state.scope, job["job_id"])).fetchall()
    retrieved = {event["snapshot_sha256"] for event in job["events"]
                 if event.get("status") == "retrieved"}
    ingested = {event["snapshot_sha256"] for event in job["events"]
                if event.get("action") == "ingest" and event.get("status") == "ingested"}
    if {row[0] for row in rows} != retrieved or not ingested:
        raise ValueError("Source evidence registration integrity check failed")
    snapshots = {}
    for checksum, source_path, did_ingest in rows:
        path = Path(source_path)
        if (path.is_symlink() or not path.is_file() or _sha(path.read_bytes()) != checksum
                or did_ingest not in (0, 1) or bool(did_ingest) != (checksum in ingested)):
            raise ValueError("Source evidence integrity check failed")
        snapshots[checksum] = read_json(path)
    candidates = {}
    events = []
    covered = set()
    for event in job["events"]:
        if event.get("action") not in ("search", "fetch", "ingest"):
            continue
        events.append(copy.deepcopy(event))
        if event.get("status") not in ("retrieved", "ingested"):
            continue
        snapshot = snapshots.get(event.get("snapshot_sha256"))
        if not snapshot or snapshot.get("topic_id") != event.get("topic_id"):
            raise ValueError("Source evidence event integrity check failed")
        if event["status"] == "retrieved":
            if snapshot.get("operation") != event["action"] or snapshot.get("report") != event.get("report"):
                raise ValueError("Source evidence report integrity check failed")
        elif event["action"] == "ingest":
            merged = merge_papers([_paper(candidates[key]) for key in sorted(candidates)] +
                                  [_paper(paper) for paper in snapshot["papers"]], config.get("topics"))
            candidates = {paper.key: paper.export(include_text=True) for paper in merged}
            covered.add(snapshot["topic_id"])
    actual = {key: json.loads(raw) for key, raw in state.db.execute(
        "SELECT paper_key,data FROM agent_candidates_v1 WHERE scope=? AND job_id=?",
        (state.scope, job["job_id"]))}
    if candidates != actual or {topic["id"] for topic in job["topics"]} - covered:
        raise ValueError("Source candidate evidence integrity check failed")
    # Check original figure evidence too, but do not transplant registrations or
    # their workspace-relative provenance. The caller must register figures anew.
    _registered_figures(state, job["job_id"])
    return rows, candidates, events


def _verified_original(state, config, job, item):
    snapshot = copy.deepcopy(config)
    snapshot["contact_email"] = ""  # The original export intentionally omits it.
    if read_json(Path(job["workspace"]) / "config.json") != snapshot:
        raise ValueError("Supersede requires the exact original configuration and storage paths")
    expected = (Path(config["state_path"]).resolve().parent / "agent-jobs" /
                _sha(state.scope.encode())[:16] / job["job_id"])
    if Path(job["workspace"]).resolve() != expected or Path(job["workspace"]).is_symlink():
        raise ValueError("Source workspace does not match this audience ledger")
    if not item or job.get("delivery") != "connector" or not job.get("completed_at"):
        raise ValueError("Supersede requires a completed connector agent job")
    payload = item["payload"]
    if (payload.get("workflow") != "agent_led" or payload.get("profile_id") != config["profile_id"]
            or job.get("profile_id") != config["profile_id"] or job.get("recipient") != config["recipient"]
            or payload.get("harvest_until") != job["local_date"]):
        raise ValueError("Source connector does not match the original job and audience")
    envelope = _check_payload(item, config)
    if (envelope.get("digest_id") != job["job_id"] or any(envelope.get(key) != payload.get(key)
            for key in ("recipient", "subject", "text", "html"))):
        raise ValueError("Source connector envelope does not match its immutable payload")
    submission = Path(job["workspace"]) / "submission.json"
    checksum = job.get("submission_sha256")
    if (submission.is_symlink() or not submission.is_file() or _sha(submission.read_bytes()) != checksum
            or payload.get("agent_submission_sha256") != checksum):
        raise ValueError("Source submission integrity check failed")
    audit = read_json(payload["paths"]["audit"])
    contract = read_json(job["contract_path"])
    if (audit.get("job_contract") != contract or audit.get("decisions") != read_json(submission).get("decisions")
            or contract.get("job_id") != job["job_id"]):
        raise ValueError("Source contract/submission failed prepared audit integrity validation")
    return contract, _verified_evidence(state, config, job, audit)


def _commit_successor(state, original, successor, rows, candidates):
    """No helper here may commit; caller owns the single SQLite transaction."""
    identifier = successor["job_id"]
    state.db.execute("INSERT INTO agent_jobs_v1 VALUES(?,?,?)", (state.scope, identifier, _json(successor)))
    state.db.executemany("INSERT INTO agent_sources_v1 VALUES(?,?,?,?,?)",
                        [(state.scope, identifier, checksum, path, ingested) for checksum, path, ingested in rows])
    state.db.executemany("INSERT INTO agent_candidates_v1 VALUES(?,?,?,?)",
                        [(state.scope, identifier, key, _json(value)) for key, value in candidates.items()])
    changed = state.db.execute(
        "UPDATE deliveries_v2 SET status='superseded',updated_at=? WHERE scope=? AND id=? AND status='prepared'",
        (successor["created_at"], state.scope, original["job_id"]))
    if changed.rowcount != 1:
        raise ValueError("Original preparation is no longer unclaimed; no supersession was committed")
    original = copy.deepcopy(original)
    original.update(status="superseded", superseded_by=identifier, superseded_reason=successor["supersede_reason"])
    state.db.execute("UPDATE agent_jobs_v1 SET data=? WHERE scope=? AND id=?",
                     (_json(original), state.scope, original["job_id"]))


def supersede_job(config, identifier, reason):
    """Create one durable replacement for an unclaimed connector preparation.

    Publication window and local day stay frozen. A stale replacement still cannot
    be claimed. Repeating the same original ID and reason returns the same job.
    """
    if not is_agent(config):
        raise ValueError("Supersede requires workflow.mode=agent")
    reason = _text(reason, "supersede reason", 1000, 8)
    state = State(config["state_path"], scope=state_scope(config))
    try:
        with state.lock():
            job = _load(state, config, identifier)
            item = state.get(identifier)
            if job["status"] not in ("completed", "superseded"):
                raise ValueError("Supersede requires a completed connector agent job")
            if state.send_claim(identifier) or state.receipt(identifier) is not None:
                raise ValueError("Source has a send claim or receipt; never supersede or reset it")
            if not item or item["status"] != ("superseded" if job["status"] == "superseded" else "prepared"):
                raise ValueError("Only a precisely prepared, never-claimed connector outbox can be superseded")
            contract, (rows, candidates, events) = _verified_original(state, config, job, item)
            successor_id = _sha(_json(["agent-supersede-v1", state.scope, identifier, reason]).encode())[:32]
            if job["status"] == "superseded":
                if job.get("superseded_by") != successor_id or job.get("superseded_reason") != reason:
                    raise ValueError("Original was already superseded with a different reason; resume its existing successor")
                successor = _load(state, config, successor_id)
                if successor.get("supersedes") != identifier or successor.get("supersede_reason") != reason:
                    raise ValueError("Successor identity integrity check failed")
                return {**_public(_refresh_result(state, successor)), "reused_supersession": True}
            if any(entry["id"] != identifier for entry in state.open_deliveries()):
                raise ValueError("Other open deliveries must be reconciled before superseding this preparation")
            if state.get(successor_id) or state.db.execute(
                    "SELECT 1 FROM agent_jobs_v1 WHERE scope=? AND id=?", (state.scope, successor_id)).fetchone():
                raise ValueError("Successor identity already exists; reconcile without overwriting it")
            directory = Path(job["workspace"]).parent / successor_id
            if directory.exists() or directory.is_symlink():
                raise ValueError("An unregistered successor workspace exists; reconcile without overwriting it")
            contract = copy.deepcopy(contract)
            old_command = json.dumps(contract["tool_argv"], ensure_ascii=False)
            contract.update(job_id=successor_id, supersedes=identifier, supersede_reason=reason,
                            research_window_end=job.get("research_window_end", job["created_at"]))
            contract["tool_argv"] = [contract["tool_argv"][0], str(directory / "tool.py"), "agent-tool", successor_id]
            old_task = (Path(job["workspace"]) / "TASK.md").read_text(encoding="utf-8")
            if old_task.count(old_command) != 1:
                raise ValueError("Source task tool command integrity check failed")
            task = old_task.replace(old_command, json.dumps(contract["tool_argv"], ensure_ascii=False))
            task += ("\n## Replacement of an unclaimed preparation\n\n"
                     "Registered source evidence and candidates were integrity-checked and reused. "
                     "Review and submit the corrected research result. Figure registrations were not copied; "
                     "register needed figures again. The original bundle remains immutable and cannot be sent.\n")
            artifacts = {"contract.json": _json(contract), "TASK.md": task,
                         "config.json": (Path(job["workspace"]) / "config.json").read_text(encoding="utf-8"),
                         "tool.py": (Path(job["workspace"]) / "tool.py").read_text(encoding="utf-8")}
            events.append({"action": "supersede", "status": "explicitly_requested", "supersedes": identifier, "reason": reason})
            successor = {**contract, "status": "awaiting_agent", "workspace": str(directory),
                         "task_path": str(directory / "TASK.md"), "contract_path": str(directory / "contract.json"),
                         "config_fingerprint": job["config_fingerprint"],
                         "contract_hashes": {name: _sha(body.encode()) for name, body in artifacts.items()},
                         "created_at": datetime.now(timezone.utc).isoformat(), "events": events}
            temporary = Path(tempfile.mkdtemp(prefix=".supersede-", dir=directory.parent))
            published = False
            try:
                for name, body in artifacts.items():
                    atomic_write(temporary / name, body)
                # BEGIN occurs after all _load/_schema calls (executescript commits).
                # Publish files before commit so a durable successor is never missing
                # its contract. A process crash may leave an orphan, which is refused.
                state.db.execute("BEGIN IMMEDIATE")
                _commit_successor(state, job, successor, rows, candidates)
                temporary.rename(directory)
                published = True
                state.db.commit()
            except BaseException:
                state.db.rollback()
                if published:
                    shutil.rmtree(directory)
                raise
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
            return {**_public(successor), "reused_supersession": False,
                    "next": "Review the reused evidence, re-register needed figures, validate and finalize the successor. No email was sent."}
    finally:
        state.close()
