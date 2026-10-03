from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .analysis import analyze, compose_overview
from .http import HttpClient, RetrievalError
from .mail import send_smtp
from .models import TRACKS
from .relevance import merge_papers
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
    return hashlib.sha256(json.dumps({k: v for k, v in config.items() if k not in ignored}, sort_keys=True).encode()).hexdigest()


def verify_payload_config(payload, config):
    if payload.get("recipient", "").lower() != config["recipient"].lower():
        raise ValueError("Prepared digest recipient does not match this profile")
    if payload.get("config_fingerprint") != config_fingerprint(config):
        raise ValueError("Prepared digest settings changed or belong to a legacy version. Restore the original settings or generate a new digest on the next local day; no stale draft was sent.")


def atomic_write(path, content):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(path)


def write_outputs(config, id_, text, html, audit, suffix=""):
    output = Path(config["output_dir"])
    output.mkdir(parents=True, exist_ok=True)
    stem = output / (audit["meta"]["local_date"] + "_" + id_ + suffix)
    paths = {}
    for ext, body in (("txt", text), ("html", html), ("json", json.dumps(audit, ensure_ascii=False, indent=2))):
        path = str(stem) + "." + ext
        atomic_write(path, body)
        paths[ext] = path
    return paths


def run(config, send=False, now=None, http=None, fetchers=None, mail_adapter=send_smtp):
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
            all_papers = []
            for source in config["sources"]:
                try:
                    papers, report = fetchers[source](http, config, start.isoformat(), local_day.isoformat(), True)
                    all_papers.extend(papers)
                    meta["sources"].append(report)
                except (RetrievalError, ValueError, TypeError, KeyError) as exc:
                    meta["errors"].append(f"{source}：{exc}")
            meta["retrieved"] = len(all_papers)
            if meta["errors"]:
                meta["failure"] = True
                text, html = render([], meta, config)
                paths = write_outputs(config, id_, text, html, {"meta": meta, "papers": []}, "_FAILED")
                return {"status": "retrieval_failed", "digest_id": id_, "errors": meta["errors"], "paths": paths}
            candidates, excluded = [], []
            for p in merge_papers(all_papers, config.get("topics")):
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
            selected = []
            counts = {k: 0 for k in ([t["id"] for t in config["topics"]] if config.get("topics") else TRACKS)}
            for p in candidates:
                # A cross-track paper appears in both sections, but is sent once.
                if all(counts[t] < config["max_papers_per_track"] for t in p.tracks):
                    selected.append(p)
                    for t in p.tracks:
                        counts[t] += 1
                else:
                    meta["deferred"] += 1
            for p in selected:
                if config["fetch_full_text"] or config.get("images", {}).get("mode", "off") != "off":
                    enrich_full_text(p, http, config)
                attach_figures(p, config)
                p.analysis = analyze(p, config, http)
            overview = compose_overview(selected, config, http)
            text, html = render(selected, meta, config, overview)
            audit = {"meta": meta, "overview": overview, "papers": [p.export() for p in selected], "excluded": excluded}
            paths = write_outputs(config, id_, text, html, audit, "" if send else "_preview")
            if not send:
                return {"status": "dry_run", "digest_id": id_, "paper_count": len(selected), "paths": paths}
            payload = {"recipient": config["recipient"], "profile_id": config.get("profile_id", "default"), "config_fingerprint": config_fingerprint(config), "subject": f"{'科研文献精选' if config.get('language', 'zh').startswith('zh') else 'Literature digest'} | {local_day.isoformat()} | {len(selected)}", "text": text, "html": html, "aliases": sorted({a for p in selected for a in p.aliases}), "harvest_until": local_day.isoformat(), "paths": paths}
            prepared = state.prepare(id_, payload)
            mail_adapter(prepared["payload"], config, state, id_)
            return {"status": "sent", "digest_id": id_, "paper_count": len(selected), "paths": paths}
    finally:
        state.close()
