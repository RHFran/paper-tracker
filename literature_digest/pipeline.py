from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .analysis import (ANALYSIS_POLICY, ModelAnalysisError, analyze, compose_overview,
                       require_analysis_payload, require_llm, screen_candidates)
from .http import HttpClient, RetrievalError
from .mail import send_smtp
from .models import TRACKS
from .references import EXPORT_VERSION, reference_files, reference_manifest, validate_reference_files
from .relevance import merge_papers, screening_tracks
from .render import render
from .sources import enrich_full_text, fetch_crossref, fetch_europepmc, fetch_arxiv, attach_figures
from .state import State, state_scope

FETCHERS = {"crossref": fetch_crossref, "europepmc": fetch_europepmc, "arxiv": fetch_arxiv}


def verified_online_date(paper):
    # Reconcile provider metadata: only day-precision electronic dates are usable.
    # Retain unknown, partial, print-only and inferred dates as excluded audit leads.
    candidates = []
    for source in paper.provenance:
        fields = source.get("date_fields", {})
        online = fields.get("published-online", {}).get("date-parts", [[]])[0]
        if len(online) == 3:
            try:
                candidates.append((date(*online), "Crossref published-online"))
            except (ValueError, TypeError):
                pass
        posted = fields.get("posted", {}).get("date-parts", [[]])[0]
        if len(posted) == 3 and source.get("type") == "posted-content":
            try:
                candidates.append((date(*posted), "Crossref posted (preprint)"))
            except (ValueError, TypeError):
                pass
        arxiv = fields.get("arxiv-published", "")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", arxiv):
            try:
                candidates.append((date.fromisoformat(arxiv), "arXiv first submission (preprint)"))
            except ValueError:
                pass
        epmc = fields.get("electronicPublicationDate", "")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", epmc):
            try:
                candidates.append((date.fromisoformat(epmc), "Europe PMC electronicPublicationDate"))
            except ValueError:
                pass
    if not candidates:
        return None
    days = {d for d, _ in candidates}
    if len(days) != 1:
        paper.warnings.append("来源的线上发表日期不一致，已暂缓收录，需人工核实")
        return None
    verified, label = candidates[0]
    paper.publication_date, paper.publication_date_label = verified.isoformat(), label
    return verified


def digest_id(config, local_day):
    identity = json.dumps({"day": local_day.isoformat(), "scope": state_scope(config), "timezone": config["timezone"]}, sort_keys=True)
    return hashlib.sha256(identity.encode()).hexdigest()[:32]


def config_fingerprint(config):
    ignored = {"state_path", "output_dir", "mail", "contact_email", "http_timeout_seconds", "http_retries", "schedule"}
    if config.get("workflow", {}).get("mode", "standalone") == "standalone":
        ignored |= {"workflow", "agent"}
    normalized = {k: v for k, v in config.items() if k not in ignored}
    if "agent" in normalized:
        normalized["agent"] = {k: v for k, v in normalized["agent"].items() if not (k == "reasoning_effort" and not v)}
    return hashlib.sha256(json.dumps({"reference_export_version": EXPORT_VERSION, "config": normalized}, sort_keys=True).encode()).hexdigest()


def verify_payload_config(payload, config):
    if config.get("workflow", {}).get("mode") != "agent":
        require_llm(config)
    require_analysis_payload(payload)
    if payload.get("transport") == "connector":
        raise ValueError("Connector outbox cannot be sent by SMTP; use its explicit transport workflow")
    if payload.get("recipient", "").lower() != config["recipient"].lower():
        raise ValueError("Prepared digest recipient does not match this profile")
    validate_reference_files(payload.get("reference_files", []))
    if payload.get("config_fingerprint") != config_fingerprint(config):
        raise ValueError("Prepared digest settings changed or belong to a legacy version. Restore the original settings or generate a new digest on the next local day; no stale draft was sent.")


def atomic_write(path, content):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    # Preserve snapshot bytes and hashes on Windows as well as POSIX.
    tmp.write_bytes(content.encode("utf-8"))
    tmp.chmod(0o600)
    tmp.replace(path)


def write_outputs(config, id_, text, html, audit, suffix="", references=None):
    output = Path(config["output_dir"])
    output.mkdir(parents=True, exist_ok=True)
    stem = output / (audit["meta"]["local_date"] + "_" + id_ + suffix)
    paths = {}
    for ext, body in (("txt", text), ("html", html), ("json", json.dumps(audit, ensure_ascii=False, indent=2))):
        path = str(stem) + "." + ext
        atomic_write(path, body)
        paths[ext] = path
    if not references:
        for extension in ("ris", "bib"):
            Path(str(stem) + "." + extension).unlink(missing_ok=True)
    for item in references or []:
        path = str(output / item["filename"])
        atomic_write(path, item["content"])
        paths[item["format"]] = path
    return paths


def _save_library(config, state, papers, identifier, paths):
    """Keep an immutable audit copy even when ordinary preview names are reused."""
    from .library import save_papers
    if paths.get("audit"):
        save_papers(state, papers, identifier, paths)
        return
    original = Path(paths["json"])
    content = original.read_bytes()
    checksum = hashlib.sha256(content).hexdigest()
    directory = Path(config["output_dir"]) / "library-audits"
    directory.mkdir(parents=True, exist_ok=True)
    frozen = directory / (checksum + ".json")
    try:
        with frozen.open("xb") as handle:
            handle.write(content)
        frozen.chmod(0o600)
    except FileExistsError:
        if frozen.is_symlink() or frozen.read_bytes() != content:
            raise ValueError("Saved library audit failed integrity validation")
    paths["library_audit"] = str(frozen.resolve())
    save_papers(state, papers, identifier, {**paths, "audit": str(frozen.resolve())})


def run(config, send=False, now=None, http=None, fetchers=None, mail_adapter=send_smtp, prepare_connector=False):
    if config.get("workflow", {}).get("mode") == "agent":
        raise ValueError("Agent mode must use the agent job runner, not the standalone pipeline")
    if send and prepare_connector:
        raise ValueError("Cannot send SMTP and prepare connector simultaneously")
    # Reject incomplete setup before retrieval, model charges, report or state writes.
    require_llm(config)
    now = now or datetime.now(ZoneInfo(config["timezone"]))
    local_now = now.astimezone(ZoneInfo(config["timezone"]))
    local_day = local_now.date()
    id_ = digest_id(config, local_day)
    http = http or HttpClient(config["contact_email"], config["http_timeout_seconds"], config["http_retries"])
    fetchers = fetchers or FETCHERS
    state = State(config["state_path"], scope=state_scope(config))
    try:
        with state.lock():
            existing = state.get(id_)
            if prepare_connector and existing:
                from .connector_delivery import prepared_result
                return prepared_result(existing, config)
            if prepare_connector and state.open_deliveries():
                raise RuntimeError("An earlier outbox is pending; reconcile it before preparing another connector envelope")
            if send and state.unresolved():
                raise RuntimeError("存在发送结果不确定的日报；先运行 status 核对，再用 resolve 人工处理，禁止自动重发")
            prior_same_day = state.sent_on(local_day.isoformat()) if send else None
            if prior_same_day:
                return {"status": "already_sent", "digest_id": prior_same_day}
            if send and existing:
                if existing["status"] == "sent":
                    return {"status": "already_sent", "digest_id": id_}
                verify_payload_config(existing["payload"], config)
                mail_adapter(existing["payload"], config, state, id_)
                return {"status": "sent", "digest_id": id_, "reused_prepared_outbox": True}
            checkpoint = state.checkpoint()
            initial = not checkpoint
            window_start = local_now - timedelta(days=config["publication_window_days"])
            publication_start = window_start.date()
            # Rescan the whole current publication window every day. This intentionally
            # captures late-indexed metadata, corrections and unsent overflow candidates.
            start = publication_start
            # Clock rollback must not create an inverted source request.
            start = min(start, local_day)
            meta = {"local_date": local_day.isoformat(), "timezone": config["timezone"], "publication_start": publication_start.isoformat(), "publication_window_days": config["publication_window_days"], "window_start": window_start.isoformat(), "window_end": local_now.isoformat(), "date_precision_note": "Day-resolution sources include the boundary calendar date; exact elapsed-hour membership is unknown", "retrieval_mode": "rolling_publication_window", "retrieval_start": start.isoformat(), "retrieval_end": local_day.isoformat(), "initial": initial, "profile_id": config.get("profile_id", "default"), "language": config.get("language", "zh-CN"), "sources": [], "errors": [], "retrieved": 0, "relevant": 0, "date_unknown": 0, "outside_window": 0, "already_sent": 0, "deferred": 0}
            retrieval_config = config
            if config["llm"].get("plan_queries", False):
                try:
                    from .query_planning import plan_queries
                    retrieval_config = plan_queries(config, http)
                    meta["query_plan"] = retrieval_config["topics"]
                except (RetrievalError, ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
                    state.pause_model_failure(local_day.isoformat(), config_fingerprint(config), "Model query planning failed validation")
                    raise ModelAnalysisError("Model query planning failed; no retrieval or delivery completed") from None
            all_papers = []
            for source in config["sources"]:
                try:
                    papers, report = fetchers[source](http, retrieval_config, start.isoformat(), local_day.isoformat(), True)
                    all_papers.extend(papers)
                    meta["sources"].append(report)
                    if report.get("truncated") or report.get("complete") is False:
                        meta["partial_coverage"] = True
                except (RetrievalError, ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
                    meta["errors"].append(f"{source}：{exc}")
            meta["retrieved"] = len(all_papers)
            if meta["errors"]:
                if config["llm"].get("plan_queries", False):
                    state.pause_model_failure(local_day.isoformat(), config_fingerprint(config), "Retrieval failed after paid query planning; automatic same-day retries paused")
                meta["failure"] = True
                text, html = render([], meta, config)
                paths = write_outputs(config, id_, text, html, {"meta": meta, "papers": []}, "_FAILED")
                return {"status": "retrieval_failed", "digest_id": id_, "errors": meta["errors"], "paths": paths}
            candidates, excluded = [], []
            for p in merge_papers(all_papers, config.get("topics")):
                if config["llm"].get("screen_candidates", False):
                    p.tracks = screening_tracks(p, config.get("topics"))
                if not p.tracks:
                    continue
                meta["relevant"] += 1
                if not config["include_preprints"] and "预印本" in p.kind:
                    excluded.append({"key": p.key, "title": p.title, "reason": "配置排除预印本"})
                    continue
                online = verified_online_date(p)
                if online is None:
                    meta["date_unknown"] += 1
                    excluded.append({"key": p.key, "title": p.title, "reason": "未取得一致、完整的线上发表日期", "provenance": p.provenance})
                    continue
                if not publication_start <= online <= local_day:
                    meta["outside_window"] += 1
                    excluded.append({"key": p.key, "title": p.title, "reason": "Outside configured publication window or future date", "publication_date": online.isoformat()})
                    continue
                if online == publication_start:
                    p.warnings.append(f"起始边界日 / boundary date: source has day precision ({config['publication_window_days']}-day window)")
                if state.was_sent(p):
                    meta["already_sent"] += 1
                    continue
                candidates.append(p)
            candidates.sort(key=lambda p: (p.publication_date, p.key), reverse=True)
            if config["llm"].get("screen_candidates", False):
                try:
                    candidates, screening = screen_candidates(candidates, config, http)
                    meta["model_screening"] = screening
                    if any("Deferred beyond" in decision.get("reason", "") for decision in screening):
                        meta["partial_coverage"] = True
                except (RetrievalError, ValueError, TypeError, KeyError, IndexError, AttributeError):
                    state.pause_model_failure(local_day.isoformat(), config_fingerprint(config), "Model relevance screening failed validation")
                    raise ModelAnalysisError("Model relevance screening failed; no digest was delivered") from None
            selected = []
            counts = {k: 0 for k in ([t["id"] for t in config["topics"]] if config.get("topics") else TRACKS)}
            for p in candidates:
                # A cross-track paper appears in both sections, but is sent once.
                if all(counts[t] < config["max_papers_per_track"] for t in p.tracks):
                    if config["fetch_full_text"] or config.get("images", {}).get("mode", "off") != "off":
                        enrich_full_text(p, http, config)
                    if len(p.evidence.strip()) < 12:
                        excluded.append({"key": p.key, "title": p.title,
                                         "reason": "Insufficient source evidence for required LLM analysis"})
                        continue  # Metadata-only leads must not consume analysis slots.
                    selected.append(p)
                    for t in p.tracks:
                        counts[t] += 1
                else:
                    meta["deferred"] += 1
            analyzed = []
            def model_failed(reason):
                state.pause_model_failure(local_day.isoformat(), config_fingerprint(config), reason)
                raise ModelAnalysisError(reason + " Automatic scheduled retries are paused for this local day. After correction, use run for an intentional retry.")

            for p in selected:
                attach_figures(p, config)
                p.analysis = analyze(p, config, http)
                if p.analysis.get("mode") != "llm_grounded" or not any(p.analysis.get("fields", {}).values()):
                    model_failed("Required paper analysis failed or produced no verified claims. No digest was delivered; check model access and source evidence.")
                analyzed.append(p)
            selected = analyzed
            overview = compose_overview(selected, config, http)
            if selected and overview.get("mode") != "llm_grounded":
                model_failed("Required overview synthesis failed validation. No digest was delivered; check model access.")
            state.clear_model_failure()
            meta["analysis_policy"] = ANALYSIS_POLICY
            meta["insufficient_evidence"] = sum(item["reason"] == "Insufficient source evidence for required LLM analysis" for item in excluded)
            suffix = "" if send or prepare_connector else "_preview"
            references = reference_files(selected, local_day.isoformat() + "_" + id_ + suffix)
            meta["reference_exports"] = reference_manifest(references)
            text, html = render(selected, meta, config, overview)
            audit = {"meta": meta, "overview": overview, "papers": [p.export() for p in selected], "excluded": excluded}
            paths = {} if prepare_connector else write_outputs(config, id_, text, html, audit, suffix, references)
            if not send and not prepare_connector:
                _save_library(config, state, selected, id_, paths)
                return {"status": "dry_run", "digest_id": id_, "paper_count": len(selected), "paths": paths}
            # Local reports use sibling downloads; mail uses real MIME attachments.
            text, html = render(selected, {**meta, "reference_delivery": "attachments"}, config, overview)
            payload = {"analysis_policy": ANALYSIS_POLICY, "reference_files": references, "recipient": config["recipient"], "profile_id": config.get("profile_id", "default"), "config_fingerprint": config_fingerprint(config), "subject": f"{'科研文献精选' if config.get('language', 'zh').startswith('zh') else 'Literature digest'} | {local_day.isoformat()} | {len(selected)}", "text": text, "html": html, "aliases": sorted({a for p in selected for a in p.aliases}), "harvest_until": local_day.isoformat(), "paths": paths}
            if prepare_connector:
                from .connector_delivery import prepare_payload
                # Retain complete machine-retrieved evidence privately for audit;
                # only RIS/BibTeX are passed as email attachments.
                audit["papers"] = [p.export(include_text=True) for p in selected]
                result = prepare_payload(config, state, id_, payload, audit)
                _save_library(config, state, selected, id_, result["paths"])
                return result
            prepared = state.prepare(id_, payload)
            _save_library(config, state, selected, id_, paths)
            mail_adapter(prepared["payload"], config, state, id_)
            return {"status": "sent", "digest_id": id_, "paper_count": len(selected), "paths": paths}
    finally:
        state.close()
