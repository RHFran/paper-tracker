"""Strict public configuration: operator settings plus isolated reader profiles."""
from __future__ import annotations

import copy
import json
import re
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULTS = {
    "profile_id": "default",
    # Preserve old files; init and new examples explicitly choose agent mode.
    "workflow": {"mode": "standalone"},
    "agent": {"backend": "codex", "executable": "", "model": "", "reasoning_effort": "", "timeout_seconds": 1800},
    "retrieval_policy": "complete",
    "recipient": "researcher@example.org",
    "timezone": "Asia/Shanghai",
    "language": "zh-CN",
    "topics": None,  # Retains the v1 two-topic behavior for existing configurations.
    "schedule": {"time": "08:30", "weekdays": [0, 1, 2, 3, 4, 5, 6], "dates": None, "catch_up": True},
    "publication_window_days": 7,
    "state_path": "state/digest.sqlite3",
    "output_dir": "output",
    "contact_email": "",
    "sources": ["crossref", "europepmc"],
    "page_size": 100,
    "max_pages_per_query": 20,
    "http_timeout_seconds": 45,
    "http_retries": 3,
    "fetch_full_text": False,
    "include_preprints": True,
    "max_papers_per_track": 20,
    "images": {"mode": "off", "max_per_paper": 3},
    "figure_catalog": {},
    "llm": {"enabled": False, "backend": "api", "cli_executable": "", "cli_model": "", "cli_timeout_seconds": 180, "screen_candidates": False, "plan_queries": False, "max_screen_candidates": 50, "base_url_env": "LITERATURE_LLM_BASE_URL", "api_key_env": "LITERATURE_LLM_API_KEY", "model_env": "LITERATURE_LLM_MODEL", "max_evidence_chars": 60000},
    "mail": {"enabled": False, "host_env": "LITERATURE_SMTP_HOST", "port": 465, "security": "ssl", "user_env": "LITERATURE_SMTP_USER", "password_env": "LITERATURE_SMTP_PASSWORD", "from_env": "LITERATURE_MAIL_FROM"},
}
PROFILE_FIELDS = {"workflow", "agent", "retrieval_policy", "llm", "id", "recipient", "timezone", "language", "topics", "schedule", "images", "publication_window_days", "include_preprints", "max_papers_per_track"}
ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def valid_email(value: str) -> bool:
    return isinstance(value, str) and len(value) <= 254 and not any(ord(c) < 32 or ord(c) == 127 for c in value) and re.fullmatch(r"[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+", value) is not None


def _positive(value, label, maximum=100000):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{label} must be an integer between 1 and {maximum}")


def _strings(value, label, required=False):
    if not isinstance(value, list) or (required and not value) or len(value) > 100:
        raise ValueError(f"{label} must be a list of 1–100 strings" if required else f"{label} must be a list of strings")
    if any(not isinstance(s, str) or not s.strip() or len(s) > 500 or any(ord(c) < 32 for c in s) for s in value):
        raise ValueError(f"{label} contains an invalid or empty string")


def _merge(base, supplied):
    result = copy.deepcopy(base)
    for key, value in supplied.items():
        if key in ("llm", "mail", "schedule", "images", "workflow", "agent"):
            if not isinstance(value, dict) or set(value) - set(DEFAULTS[key]) - ({"reuse_context"} if key == "images" else set()):
                raise ValueError(f"Invalid or unknown {key} settings")
            if key == "schedule":
                # A profile can change calendar mode without accidentally retaining
                # its parent's selector. Explicitly supplying both is ambiguous.
                if value.get("dates") is not None and value.get("weekdays") is not None:
                    raise ValueError("Use either schedule.dates or schedule.weekdays, not both")
                if value.get("dates") is not None:
                    result[key]["weekdays"] = None
                elif value.get("weekdays") is not None:
                    result[key]["dates"] = None
            result[key].update(value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def validate_config(c):
    if not isinstance(c["profile_id"], str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", c["profile_id"]):
        raise ValueError("Profile id must be 1–64 letters, digits, hyphens or underscores")
    if not valid_email(c["recipient"]):
        raise ValueError("recipient must be a single email address")
    if c["contact_email"] and not valid_email(c["contact_email"]):
        raise ValueError("contact_email must be a single email address")
    try:
        ZoneInfo(c["timezone"])
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        raise ValueError("timezone must be an installed IANA timezone, e.g. Asia/Shanghai") from None
    if not isinstance(c["language"], str) or not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", c["language"]):
        raise ValueError("language must be a language tag, e.g. zh-CN, en, de or ja")
    if c.get("retrieval_policy", "complete") not in ("complete", "bounded"):
        raise ValueError("retrieval_policy must be complete or bounded")
    if not isinstance(c["sources"], list) or not c["sources"] or any(not isinstance(source, str) for source in c["sources"]) or set(c["sources"]) - {"crossref", "europepmc", "arxiv"}:
        raise ValueError("sources must contain crossref, europepmc and/or arxiv")
    if len(c["sources"]) != len(set(c["sources"])):
        raise ValueError("Duplicate sources are not allowed")
    for key, maximum in {"publication_window_days": 3650, "page_size": 1000, "max_pages_per_query": 1000, "max_papers_per_track": 100, "http_timeout_seconds": 300, "http_retries": 10}.items():
        _positive(c[key], key, maximum)
    for key in ("fetch_full_text", "include_preprints"):
        if type(c[key]) is not bool:
            raise ValueError(f"{key} must be true or false")
    for key in ("llm", "mail"):
        if type(c[key]["enabled"]) is not bool:
            raise ValueError(f"{key}.enabled must be true or false")
        for name, value in c[key].items():
            if name.endswith("_env") and (not isinstance(value, str) or not ENV_NAME.fullmatch(value)):
                raise ValueError(f"{key}.{name} must be an environment variable name, never a secret")
    if c.get("workflow", {}).get("mode", "standalone") not in ("agent", "standalone"):
        raise ValueError("workflow.mode must be agent or standalone")
    agent = c.get("agent", DEFAULTS["agent"])
    if agent.get("backend") not in ("codex", "claude", "host"):
        raise ValueError("agent.backend must be codex, claude or host")
    for name in ("executable", "model"):
        value = agent.get(name, "")
        if not isinstance(value, str) or len(value) > 2000 or any(ord(char) < 32 for char in value):
            raise ValueError("agent." + name + " must be a single-line string")
    effort = agent.get("reasoning_effort", "")
    efforts = {"codex": {"", "none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"},
               "claude": {"", "low", "medium", "high", "xhigh", "max", "ultracode"},
               "host": {"", "none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra", "ultracode"}}
    if not isinstance(effort, str) or effort not in efforts[agent["backend"]]:
        raise ValueError("agent.reasoning_effort is unsupported for the selected backend; model/client availability still requires a live test")
    _positive(agent.get("timeout_seconds", 1800), "agent.timeout_seconds", 7200)
    llm = c["llm"]
    if llm.get("backend", "api") not in ("api", "codex", "claude"):
        raise ValueError("llm.backend must be api, codex or claude")
    for name in ("cli_executable", "cli_model"):
        value = llm.get(name, "")
        if not isinstance(value, str) or len(value) > 2000 or any(ord(char) < 32 for char in value):
            raise ValueError("llm." + name + " must be a single-line string")
    _positive(llm.get("cli_timeout_seconds", 180), "llm.cli_timeout_seconds", 1800)
    _positive(llm.get("max_screen_candidates", 50), "llm.max_screen_candidates", 200)
    if type(llm.get("plan_queries", False)) is not bool:
        raise ValueError("llm.plan_queries must be true or false")
    if type(llm.get("screen_candidates", False)) is not bool:
        raise ValueError("llm.screen_candidates must be true or false")
    _positive(c["llm"]["max_evidence_chars"], "llm.max_evidence_chars", 500000)
    if c["llm"]["max_evidence_chars"] < 100:
        raise ValueError("llm.max_evidence_chars must be at least 100")
    if c["mail"]["security"] not in ("ssl", "starttls"):
        raise ValueError("Only encrypted SMTP is supported: ssl or starttls")
    _positive(c["mail"]["port"], "mail.port", 65535)
    if c["images"]["mode"] not in ("off", "links", "embed"):
        raise ValueError("images.mode must be off, links or embed")
    _positive(c["images"]["max_per_paper"], "images.max_per_paper", 10)
    if c["images"].get("reuse_context", "general") not in ("general", "personal_noncommercial"):
        raise ValueError("images.reuse_context must be general or personal_noncommercial")
    if not isinstance(c["figure_catalog"], dict):
        raise ValueError("figure_catalog must be an object keyed by canonical paper identifiers")
    for key, figures in c["figure_catalog"].items():
        if not isinstance(key, str) or not isinstance(figures, list) or len(figures) > 20:
            raise ValueError("figure_catalog entries must be lists of up to 20 figures")
        for figure in figures:
            allowed = {"id", "caption", "url", "source_url", "license", "license_scope", "attribution"}
            if not isinstance(figure, dict) or set(figure) - allowed or any(not isinstance(v, str) or len(v) > 2000 for v in figure.values()):
                raise ValueError("figure_catalog figure metadata must use supported text fields")
            if figure.get("license_scope", "unknown") not in ("figure", "unknown", "article"):
                raise ValueError("Figure license_scope must be figure, article or unknown")
    s = c["schedule"]
    if not isinstance(s["time"], str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", s["time"]):
        raise ValueError("schedule.time must be HH:MM in the profile timezone")
    dates, weekdays = s.get("dates"), s.get("weekdays")
    if dates is not None:
        if weekdays is not None:
            raise ValueError("Use either schedule.dates or schedule.weekdays, not both")
        if not isinstance(dates, list) or not 1 <= len(dates) <= 1000:
            raise ValueError("schedule.dates must contain 1–1000 unique dates in YYYY-MM-DD format")
        for day in dates:
            try:
                if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
                    raise ValueError
            except (ValueError, TypeError):
                raise ValueError("schedule.dates must contain valid dates in YYYY-MM-DD format") from None
        if len(set(dates)) != len(dates):
            raise ValueError("schedule.dates must not contain duplicate dates")
    elif not isinstance(weekdays, list) or not weekdays or any(type(d) is not int or not 0 <= d <= 6 for d in weekdays) or len(set(weekdays)) != len(weekdays):
        raise ValueError("schedule.weekdays must be unique integers 0=Monday through 6=Sunday")
    if type(s["catch_up"]) is not bool:
        raise ValueError("schedule.catch_up must be true or false")
    if c["topics"] is not None:
        if not isinstance(c["topics"], list) or not 1 <= len(c["topics"]) <= 25:
            raise ValueError("topics must contain 1–25 topic objects")
        ids = set()
        for topic in c["topics"]:
            if not isinstance(topic, dict) or set(topic) - {"id", "name", "queries", "include_any", "include_all", "exclude_any", "source_queries"}:
                raise ValueError("Invalid topic fields")
            tid = topic.get("id", "")
            if not isinstance(tid, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", tid) or tid in ids:
                raise ValueError("Each topic needs a unique safe id")
            ids.add(tid)
            _strings([topic.get("name", "")], "topic.name", True)
            _strings(topic.get("queries"), "topic.queries", True)
            for field in ("include_any", "include_all", "exclude_any"):
                _strings(topic.get(field, []), f"topic.{field}")
            overrides = topic.get("source_queries", {})
            if not isinstance(overrides, dict) or set(overrides) - {"crossref", "europepmc", "arxiv"}:
                raise ValueError("topic.source_queries has an unsupported source")
            for source, queries in overrides.items():
                _strings(queries, f"source_queries.{source}", True)
    for key in ("state_path", "output_dir"):
        if not isinstance(c[key], str) or not c[key] or "\x00" in c[key]:
            raise ValueError(f"{key} must be a path")
    return c


def load_configs(path: str) -> list[dict]:
    p = Path(path).resolve()
    supplied = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(supplied, dict):
        raise ValueError("Configuration must be a JSON object")
    unknown = set(supplied) - set(DEFAULTS) - {"profiles"}
    if unknown:
        raise ValueError("Unknown configuration fields: " + ", ".join(sorted(unknown)))
    profiles = supplied.pop("profiles", None)
    base = _merge(DEFAULTS, supplied)
    if profiles is None:
        configurations = [validate_config(base)]
    else:
        if not isinstance(profiles, list) or not profiles or len(profiles) > 100:
            raise ValueError("profiles must contain 1–100 reader profiles")
        configurations, seen = [], set()
        for profile in profiles:
            if not isinstance(profile, dict) or set(profile) - PROFILE_FIELDS:
                raise ValueError("Reader profiles may only override reader settings")
            profile = dict(profile)
            identifier = profile.pop("id", "")
            if not isinstance(identifier, str):
                raise ValueError("Profile id must be text")
            if identifier in seen:
                raise ValueError("Profile ids must be unique")
            seen.add(identifier)
            c = _merge(base, {**profile, "profile_id": identifier})
            validate_config(c)
            # Isolate all outboxes, checkpoints, paper deduplication and previews by reader.
            state = Path(c["state_path"])
            c["state_path"] = str(state.parent / identifier / state.name)
            c["output_dir"] = str(Path(c["output_dir"]) / identifier)
            configurations.append(c)
    for c in configurations:
        for key in ("state_path", "output_dir"):
            c[key] = str((p.parent / c[key]).resolve())
    return configurations


def load_config(path: str, profile: str | None = None) -> dict:
    configs = load_configs(path)
    if profile:
        configs = [c for c in configs if c["profile_id"] == profile]
        if not configs:
            raise ValueError("Unknown profile id")
    if len(configs) != 1:
        raise ValueError("This config has multiple profiles; select one with --profile")
    return configs[0]
