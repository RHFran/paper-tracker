"""Reader onboarding and an explicit opt-in operator delivery workflow."""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import DEFAULTS, load_configs, validate_config
from .analysis import require_llm
from .mail import send_smtp
from .pipeline import config_fingerprint, run, verify_payload_config
from .schedule import is_due, next_run
from .state import State, state_scope


def initialize(args, input_fn=input):
    path = Path(args.config)
    if path.exists():
        raise ValueError("Config already exists; choose a new --config path or edit it. Nothing was overwritten.")
    def answer(value, prompt, default=None):
        if value is not None:
            return value
        if args.yes:
            if default is None:
                raise ValueError(f"Missing {prompt}; provide command options without interactive input")
            return default
        entered = input_fn(f"{prompt}" + (f" [{default}]" if default else "") + ": ").strip()
        return entered or default
    recipient = answer(args.recipient, "Destination email")
    directions = args.topic or [answer(None, "Research direction (English keywords improve source matching)")]
    language = answer(args.language, "Preferred language tag", "zh-CN")
    zone = answer(args.timezone, "IANA timezone", "Asia/Shanghai")
    at = answer(args.at, "Daily send time HH:MM", "08:30")
    topics = [{"id": f"topic-{i}", "name": topic, "queries": [topic], "include_any": [], "include_all": [], "exclude_any": []} for i, topic in enumerate(directions, 1)]
    config = {"recipient": recipient, "language": language, "timezone": zone, "topics": topics, "schedule": {"time": at, "weekdays": list(range(7)), "catch_up": True}, "images": {"mode": "off", "max_per_paper": 3}, "llm": {"enabled": False}, "mail": {"enabled": False}}
    checked = copy.deepcopy(DEFAULTS)
    for key, value in config.items():
        if isinstance(value, dict):
            checked[key].update(value)
        else:
            checked[key] = value
    validate_config(checked)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents overwriting a file created while the wizard was open.
    with path.open("x", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return {"status": "configured", "path": str(path.resolve()), "next": "preview (offline demo), then configure and enable the required LLM before run (live dry-run). Configure SMTP separately before explicit delivery.", "schedule_installed": False}


def model_readiness(config):
    try:
        require_llm(config)
    except ValueError as exc:
        return {"llm_required": True, "live_ready": False, "live_blocker": str(exc)}
    return {"llm_required": True, "live_ready": True, "live_blocker": None}


def _select(configs, profile):
    if profile:
        configs = [c for c in configs if c["profile_id"] == profile]
        if not configs:
            raise ValueError("Unknown profile id")
    return configs


def _model_pause(config, state, local_day):
    pause = state.model_failure_pause()
    if pause and pause["local_date"] == local_day.isoformat() and pause["config_fingerprint"] == config_fingerprint(config):
        return {key: value for key, value in pause.items() if key != "config_fingerprint"}
    return None


def _run_one(config, command, send=False, now=None):
    now = now or datetime.now(timezone.utc)
    if command == "tick" and not is_due(config, now):
        return {"profile_id": config["profile_id"], "status": "not_due", "next_run": next_run(config, now)}
    if command == "tick":
        require_llm(config)
        state = State(config["state_path"], scope=state_scope(config))
        try:
            pause = _model_pause(config, state, now.astimezone(ZoneInfo(config["timezone"])).date())
        finally:
            state.close()
        if pause:
            return {"profile_id": config["profile_id"], "status": "model_paused", "pause": pause}
    return {"profile_id": config["profile_id"], **run(config, send=send, now=now)}


def _many(configs, command, send=False, now=None):
    results = []
    for config in configs:
        try:
            results.append(_run_one(config, command, send, now))
        except Exception as exc:
            # Avoid exposing provider payloads/credentials from unexpected exceptions.
            results.append({"profile_id": config["profile_id"], "status": "error", "error": str(exc) if isinstance(exc, (ValueError, RuntimeError)) else type(exc).__name__})
    return results


def _report(result):
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    items = result if isinstance(result, list) else [result]
    return 1 if any(r.get("status") == "error" for r in items) else 2 if any(r.get("status") == "retrieval_failed" for r in items) else 3 if any(r.get("status") == "model_paused" for r in items) else 0


def _main(argv=None):
    parser = argparse.ArgumentParser(description="Smart Paper Tracker: research directions → evidence-aware literature email. Dry-run by default.")
    parser.add_argument("--config", default="config.json", help="Operator and reader JSON configuration")
    parser.add_argument("--profile", help="Select one profile; run/tick otherwise process all profiles")
    parser.add_argument("--env-file", help="Explicit private literal KEY=value file; no shell expansion")
    sub = parser.add_subparsers(dest="command", required=True)
    initializer = sub.add_parser("init", help="Interactive reader setup; never installs schedules or sends mail")
    initializer.add_argument("--recipient")
    initializer.add_argument("--topic", action="append", help="Repeat for multiple research directions")
    initializer.add_argument("--language")
    initializer.add_argument("--timezone")
    initializer.add_argument("--time", dest="at")
    initializer.add_argument("--yes", action="store_true", help="Noninteractive; requires recipient/topic, defaults language/timezone/time")
    model_setup = sub.add_parser("configure-model", help="Choose provider/model and enter a hidden API key; save only after local confirmation; no network")
    model_setup.add_argument("--secrets-file", help="Private .env or .env.<name>; default .env next to config")
    model_setup.add_argument("--replace", action="store_true", help="Explicitly allow replacing this subscription model and slot; still asks before saving")
    sub.add_parser("validate", help="Validate profiles, print readiness and next scheduled times without network")
    preview = sub.add_parser("preview", help="Generate a clearly labeled synthetic offline demo; no network/state/mail")
    preview.add_argument("--language", help="Override demo language")
    for command, help_ in (("run", "Retrieve and compose now"), ("tick", "Run only due profiles, once per local day when sending"), ("schedule", "Foreground minute scheduler; keep process alive, Ctrl-C to stop")):
        runner = sub.add_parser(command, help=help_ + "; dry-run by default")
        runner.add_argument("--send", action="store_true", help="Explicit delivery; still requires mail.enabled=true and SMTP configuration")
    sub.add_parser("status", help="Inspect only this audience's delivery ledger")
    resolver = sub.add_parser("resolve", help="Resolve an uncertain send after checking provider records")
    resolver.add_argument("digest_id")
    resolver.add_argument("decision", choices=["sent", "retry"])
    sender = sub.add_parser("send", help="Send an existing prepared outbox for one selected profile")
    sender.add_argument("digest_id")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            return _report(initialize(args))
        if args.command == "configure-model":
            from .configure_model import configure_model
            return _report(configure_model(args))
        configs = _select(load_configs(args.config), args.profile)
        if args.command == "validate":
            return _report([{"status": "valid", "profile_id": c["profile_id"], "recipient": c["recipient"], "language": c["language"], "timezone": c["timezone"], "next_run": next_run(c), "mail_enabled": c["mail"]["enabled"], "llm_enabled": c["llm"]["enabled"], **model_readiness(c), "missing_environment_variables": [v for section in ("mail", "llm") if c[section]["enabled"] for k, v in c[section].items() if k.endswith("_env") and not os.environ.get(v)], "schedule_installed": False} for c in configs])
        if args.command == "preview":
            from .demo import preview
            return _report([preview(c, args.language) for c in configs])
        if args.command in ("run", "tick"):
            return _report(_many(configs, args.command, args.send))
        if args.command == "schedule":
            for config in configs:
                require_llm(config)
            previews = set()
            while True:
                # Re-read non-secret reader settings without restarting the service.
                configs = _select(load_configs(args.config), args.profile)
                now = datetime.now(timezone.utc)
                due = []
                for c in configs:
                    key = (state_scope(c), now.astimezone(ZoneInfo(c["timezone"])).date())
                    if not is_due(c, now):
                        continue
                    if not args.send and key in previews:
                        continue
                    # Sent/uncertain states are terminal until user resolution; do not busy retry them.
                    if args.send:
                        state = State(c["state_path"], scope=state_scope(c))
                        try:
                            from .pipeline import digest_id
                            delivery = state.get(digest_id(c, key[1]))
                            if state.unresolved() or state.sent_on(key[1].isoformat()) or delivery and delivery["status"] == "sent" or _model_pause(c, state, key[1]):
                                continue
                        finally:
                            state.close()
                    due.append(c)
                    if not args.send:
                        previews.add(key)
                if due:
                    _report(_many(due, "tick", args.send, now))
                previews = {k for k in previews if (now.date() - k[1]).days < 2}
                time.sleep(60)
        if args.command in ("send", "resolve") and len(configs) != 1:
            raise ValueError("Select exactly one profile with --profile for send/resolve")
        results = []
        for config in configs:
            if args.command == "send":
                require_llm(config)
            state = State(config["state_path"], scope=state_scope(config))
            try:
                with state.lock():
                    if args.command == "status":
                        result = {"profile_id": config["profile_id"], "checkpoint": state.checkpoint(), "unresolved": state.unresolved(), "model_failure_pause": state.model_failure_pause(), "deliveries": state.recent()}
                    elif args.command == "resolve":
                        state.resolve(args.digest_id, args.decision)
                        result = {"digest_id": args.digest_id, "status": state.get(args.digest_id)["status"]}
                    else:
                        item = state.get(args.digest_id)
                        if state.unresolved() or not item or item["status"] != "prepared":
                            raise ValueError("Sending requires a prepared outbox and no unresolved deliveries in this profile")
                        verify_payload_config(item["payload"], config)
                        send_smtp(item["payload"], config, state, args.digest_id)
                        result = {"digest_id": args.digest_id, "status": "sent"}
                    results.append(result)
            finally:
                state.close()
        return _report(results)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"Error: {exc if isinstance(exc, (ValueError, RuntimeError, OSError)) else type(exc).__name__}", file=sys.stderr)
        return 1


def main(argv=None):
    """Load an explicitly named private environment for this call only."""
    if os.name == "nt":
        for stream in (sys.stdout, sys.stderr):
            if callable(getattr(stream, "reconfigure", None)):
                stream.reconfigure(encoding="utf-8")
    argv = list(sys.argv[1:] if argv is None else argv)
    options = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    options.add_argument("--env-file")
    options.add_argument("--config", default="config.json")
    parsed, _ = options.parse_known_args(argv)
    if not parsed.env_file or any(arg in ("--help", "-h") for arg in argv):
        return _main(argv)
    added = []
    try:
        from .environment import read_environment_file
        configs = load_configs(parsed.config)
        allowed = {value for config in configs for section in ("llm", "mail") for key, value in config[section].items() if key.endswith("_env")}
        for name, value in read_environment_file(parsed.env_file, allowed).items():
            if value and not os.environ.get(name):
                os.environ[name] = value
                added.append(name)
        return _main(argv)
    except (ValueError, OSError) as exc:
        print(f"Error: {str(exc) if isinstance(exc, ValueError) else 'Unable to read private configuration or environment file'}", file=sys.stderr)
        return 1
    finally:
        for name in added:
            os.environ.pop(name, None)


if __name__ == "__main__":
    raise SystemExit(main())
