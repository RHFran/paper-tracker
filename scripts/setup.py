#!/usr/bin/env python3
"""Safe cross-platform bootstrap. No system changes, secrets, or real sends."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def checked(command):
    subprocess.run(command, check=True, cwd=ROOT)


def main(argv=None):
    if os.name == "nt":
        for stream in (sys.stdout, sys.stderr):
            if callable(getattr(stream, "reconfigure", None)):
                stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Create/reuse .venv, preserve existing config, validate and generate an offline preview. Never send or install a scheduler.")
    parser.add_argument("--config", help="Config path; relative paths are relative to the checkout")
    parser.add_argument("--demo", action="store_true", help="Use a synthetic demo identity without questions; default config: runtime/demo/config.json")
    parser.add_argument("--api", action="store_true", help="Explicitly choose optional standalone API workflow and offer its key wizard for new configs")
    parser.add_argument("--agent-backend", choices=["codex", "claude", "host"], default="codex")
    parser.add_argument("--skip-model", action="store_true", help="Do not offer interactive model setup; live runs still require a model")
    parser.add_argument("--skip-install", action="store_true", help="Reuse an already provisioned .venv without pip/network")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 11):
        parser.error("Python 3.11 or newer is required")
    os.umask(0o077)
    config = Path(args.config or ("runtime/demo/config.json" if args.demo else "config.json"))
    if not config.is_absolute():
        config = ROOT / config
    python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    try:
        if not python.is_file():
            if args.skip_install:
                parser.error(".venv is missing; run setup once without --skip-install")
            # Refuse to replace an unknown or broken environment automatically.
            if (ROOT / ".venv").exists():
                parser.error(".venv exists but has no usable Python; inspect it before retrying")
            print("Creating an isolated Python environment in .venv...", flush=True)
            checked([sys.executable, "-m", "venv", str(ROOT / ".venv")])
        checked([str(python), "-c", "import sys; assert sys.version_info >= (3, 11), 'Python 3.11+ required'"])
        if not args.skip_install:
            print("Installing this checkout and its declared dependencies into .venv...", flush=True)
            checked([str(python), "-m", "pip", "install", "--disable-pip-version-check", "."])
        zone_check = [str(python), "-c", "from zoneinfo import ZoneInfo; ZoneInfo('UTC'); ZoneInfo('Asia/Shanghai'); ZoneInfo('America/New_York')"]
        if subprocess.run(zone_check, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
            if args.skip_install:
                parser.error("IANA timezone data missing; run setup without --skip-install or install tzdata into .venv")
            print("Installing Python tzdata because the operating system has no IANA database...", flush=True)
            checked([str(python), "-m", "pip", "install", "--disable-pip-version-check", "tzdata>=2024.1"])
            checked(zone_check)
        cli = [str(python), "-m", "literature_digest", "--config", str(config)]
        new_config = not config.exists()
        if new_config:
            command = cli + ["init", "--agent-backend", args.agent_backend]
            if args.demo:
                command += ["--yes", "--recipient", "researcher@example.org", "--topic", "forest carbon climate", "--language", "en", "--timezone", "UTC"]
            checked(command)
            if args.api:
                settings = json.loads(config.read_text(encoding="utf-8"))
                settings["workflow"] = {"mode": "standalone"}
                config.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else:
            print("Keeping the existing configuration unchanged.", flush=True)
        configured_model = False
        if args.api and not args.demo and not args.skip_model and new_config:
            print("Optional standalone API workflow: token charges depend on provider/model and paper count. Offline preview makes no model calls.", flush=True)
            if input("Configure your provider/model and enter the API key locally now? [Y/n]: ").strip().lower() not in ("n", "no"):
                checked(cli + ["configure-model"])
                configured_model = (config.parent / ".env").is_file()
        if configured_model:
            checked([str(python), str(ROOT / "scripts/launch.py"), "--env-file", str(config.parent / ".env"), "--config", str(config), "validate"])
        else:
            checked(cli + ["validate"])
        checked(cli + ["preview"])
    except subprocess.CalledProcessError as exc:
        print(f"Setup stopped (exit {exc.returncode}). Existing configuration was not overwritten. See docs/platform-setup.md for prerequisites and troubleshooting.", file=sys.stderr)
        return exc.returncode or 1
    print("\nReady: offline preview created. No mail was sent and no scheduler was installed.")
    print("Next: edit topics/schedule, select a usable Codex/Claude agent or host agent, and review account costs before a live job.")
    print("Agent mode: bash scripts/run.sh --config <your-config> run (agent.backend=codex/claude/host). Optional API: setup --api or configure-model.")
    print("API/SMTP secrets, if used: add --env-file <private-.env> before the command")
    print("Linux/macOS: bash scripts/run.sh --config <your-config> run")
    print("Windows: .\\scripts\\run.ps1 --config <your-config> run")
    print("Guide: docs/platform-setup.md (English) / docs/platform-setup_中文.md (中文)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
