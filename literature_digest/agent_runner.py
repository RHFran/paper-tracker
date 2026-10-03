"""Trigger full coding agents; completion is a validated job, never stdout prose."""
from __future__ import annotations

import os
import json
from pathlib import Path
import signal
import subprocess
import tempfile

from .agent_jobs import create_job, require_agent, _load, _public, _save
from .mail import send_smtp
from .pipeline import verify_payload_config
from .state import State, state_scope


class AgentInterrupted(RuntimeError):
    """Termination may leave tool descendants; explicit operator recovery required."""


def command(config, job):
    backend, executable, model = require_agent(config)
    roots = sorted({str(Path(config['state_path']).resolve().parent), str(Path(config['output_dir']).resolve())})
    if backend == "host":
        return None
    for root in roots:
        Path(root).mkdir(parents=True, exist_ok=True)
    effort = config["agent"].get("reasoning_effort", "")
    if backend == "codex":
        argv = [executable, "exec", "--sandbox", "workspace-write", "--cd", job["workspace"],
                "--skip-git-repo-check", "--color", "never"]
        for root in roots:
            argv += ["--add-dir", root]
        if model:
            argv += ["--model", model]
        if effort:
            argv += ["-c", "model_reasoning_effort=" + json.dumps(effort)]
        argv.append("-")
    else:
        # Preserve the user's normal permission/security settings. Print mode
        # may deny an unapproved tool; that is a blocker, never bypassed here.
        argv = [executable, "-p", "--output-format", "json"]
        for root in roots:
            argv += ["--add-dir", root]
        if model:
            argv += ["--model", model]
        if effort:
            argv += ["--effort", effort]
    return argv


def execute(argv, prompt, config, job):
    env = dict(os.environ)
    # The research agent does not need this program's API/SMTP credentials.
    # CLI-managed authentication stays where the CLI maintains it.
    for section in ("llm", "mail"):
        for name, value in config[section].items():
            if name.endswith("_env"):
                env.pop(value, None)
    kwargs = {"cwd": job["workspace"], "env": env, "stdin": subprocess.PIPE,
              "stdout": subprocess.DEVNULL, "text": True, "encoding": "utf-8", "shell": False}
    if os.name != "nt":
        kwargs["start_new_session"] = True
    # Never put agent output or provider logs into the public result. Read only
    # bounded diagnostics for safe error classification, then discard the file.
    with tempfile.TemporaryFile() as errors:
        try:
            process = subprocess.Popen(argv, stderr=errors, **kwargs)
            try:
                process.communicate(prompt, timeout=config["agent"]["timeout_seconds"])
            except subprocess.TimeoutExpired:
                try:
                    if os.name != "nt":
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                except OSError:
                    pass  # Still interrupted/uncertain; never downgrade to retryable.
                try:
                    process.communicate(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
                raise AgentInterrupted("Agent timed out; verify all agent/tool descendants have stopped, then use agent-recover --agent-stopped before retrying") from None
        except OSError:
            raise RuntimeError("Agent process could not start; inspect its installation and local permissions") from None
        if process.returncode:
            errors.seek(0)
            diagnostic = errors.read(1024 * 1024).decode("utf-8", "replace").lower()
            if "read-only file system" in diagnostic or "permission denied" in diagnostic:
                raise RuntimeError("Agent runtime or tool access is not writable/permitted; use a supported host without changing credentials or security settings")
            raise RuntimeError("Agent exited unsuccessfully; inspect CLI login, permissions, version and quota locally. Provider logs withheld")


def _deliver(config, result, mail_adapter):
    state = State(config["state_path"], scope=state_scope(config))
    try:
        with state.lock():
            item = state.get(result["digest_id"])
            if not item:
                raise ValueError("Agent did not prepare an SMTP outbox")
            if item["status"] == "sent":
                return {**result, "status": "already_sent"}
            if item["status"] != "prepared" or state.unresolved():
                raise ValueError("Delivery is uncertain or active; inspect provider records, never automatically resend")
            verify_payload_config(item["payload"], config)
            mail_adapter(item["payload"], config, state, result["digest_id"])
            return {**result, "status": "sent", "automatic_send": True}
    finally:
        state.close()


def run_agent(config, send=False, now=None, prepare_connector=False, retry=False, executor=None, mail_adapter=send_smtp):
    if send and prepare_connector:
        raise ValueError("Choose SMTP send or connector preparation, not both")
    if send and not config["mail"]["enabled"]:
        raise ValueError("SMTP delivery requires mail.enabled=true")
    delivery = "connector" if prepare_connector else "smtp" if send else "dry_run"
    job = create_job(config, now, delivery)
    # Export is useful even if a nested CLI is absent or blocked. A host agent
    # follows the same durable task/tool contract and must finalize it itself.
    if config["agent"]["backend"] == "host":
        if job["status"] == "completed":
            return _deliver(config, job["result"], mail_adapter) if send else job["result"]
        return {**job, "next": "A host agent must execute TASK.md with the supplied tools, then finalize. No research has completed or mail been sent."}
    if job["status"] == "completed":
        return _deliver(config, job["result"], mail_adapter) if send else job["result"]
    state = State(config["state_path"], scope=state_scope(config))
    try:
        with state.lock():
            record = _load(state, config, job["job_id"])
            if record["status"] in ("running", "interrupted"):
                return {**_public(record), "next": "Agent is running or was interrupted; inspect the process/job before retrying"}
            if record["status"] == "blocked" and not retry:
                return {**_public(record), "error": record["blocker"], "next": "Fix the blocker, then run --retry-agent intentionally; scheduled ticks do not retry paid work"}
            try:
                argv = command(config, record)
            except ValueError as exc:
                record.update(status="blocked", blocker=str(exc))
                _save(state, record)
                return {**_public(record), "error": str(exc)}
            record.update(status="running")
            record.pop("blocker", None)
            _save(state, record)
        failure = None
        interrupted = False
        try:
            (executor or execute)(argv, Path(job["task_path"]).read_text(encoding="utf-8"), config, job)
        except (RuntimeError, OSError) as exc:
            failure = str(exc) if isinstance(exc, RuntimeError) else "Agent execution failed"
            interrupted = isinstance(exc, AgentInterrupted)
        with state.lock():
            record = _load(state, config, job["job_id"])
            if record["status"] != "completed":
                record.update(status="interrupted" if interrupted else "blocked", blocker=failure or "Agent exited without finalizing a validated result; its text output is not completion")
                _save(state, record)
                return {**_public(record), "error": record["blocker"]}
            result = record["result"]
    finally:
        state.close()
    return _deliver(config, result, mail_adapter) if send else result
