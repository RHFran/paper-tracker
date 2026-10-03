#!/usr/bin/env python3
"""Safe cross-platform bootstrap. No system changes, secrets, or real sends."""
from __future__ import annotations

import argparse
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
            command = cli + ["init"]
            if args.demo:
                command += ["--yes", "--recipient", "researcher@example.org", "--topic", "forest carbon climate", "--language", "en", "--timezone", "UTC"]
            checked(command)
        else:
            print("Keeping the existing configuration unchanged.", flush=True)
        configured_model = False
        if not args.demo and not args.skip_model and new_config:
            print("Live digests require an LLM; token charges depend on provider/model and paper count. Offline preview is free of API calls.", flush=True)
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
    print("Next: edit your topics/schedule, configure the required LLM and optional SMTP, and inspect a live dry run.")
    print("Linux/macOS: bash scripts/run.sh --env-file <private-.env> --config <your-config> run")
    print("Windows: .\\scripts\\run.ps1 --env-file <private-.env> --config <your-config> run")
    print("Guide: docs/platform-setup.md (English) / docs/platform-setup_中文.md (中文)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
