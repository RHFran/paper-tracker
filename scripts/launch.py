#!/usr/bin/env python3
"""Launch from the checkout; optional no-echo, process-only credential input."""
from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path
import sys
import warnings

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


from literature_digest.environment import read_environment_file


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    os.chdir(ROOT)
    os.umask(0o077)
    launcher = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    launcher.add_argument("--prompt-secrets", action="store_true")
    launcher.add_argument("--env-file", help="Explicit private KEY=value file; never executed as shell code")
    options, argv = launcher.parse_known_args(argv)
    prompt = options.prompt_secrets
    from literature_digest.cli import main as cli_main
    if not argv:
        argv = ["--help"]
    if (not prompt and not options.env_file) or any(arg in ("--help", "-h") for arg in argv):
        return cli_main(argv)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--profile")
    args, rest = parser.parse_known_args(argv)
    command = rest[0] if rest else ""
    supplied = []
    try:
        from literature_digest.config import load_configs
        all_configs = load_configs(args.config)
        configs = all_configs
        if args.profile:
            configs = [c for c in configs if c["profile_id"] == args.profile]
            if not configs:
                raise ValueError("Unknown profile id")
        if options.env_file:
            allowed = {value for config in all_configs for section in ("llm", "mail") for key, value in config[section].items() if key.endswith("_env")}
            for name, value in read_environment_file(options.env_file, allowed).items():
                if value and not os.environ.get(name):
                    os.environ[name] = value
                    supplied.append(name)
        if prompt and command in ("run", "tick", "schedule", "send"):
            names = set()
            sections = ["llm"]
            if command == "send" or "--send" in rest:
                sections.append("mail")
            for config in configs:
                for section in sections:
                    if config[section]["enabled"] and (section != "llm" or config.get("workflow", {}).get("mode") != "agent" and config["llm"].get("backend", "api") == "api"):
                        names.update(value for key, value in config[section].items() if key.endswith("_env"))
            missing = sorted(name for name in names if not os.environ.get(name))
            if missing and not sys.stdin.isatty():
                raise ValueError("--prompt-secrets requires an interactive terminal; use the service's private environment instead")
            if missing:
                print("Enter provider values locally. Input is hidden; values live only in this process and are not saved.", file=sys.stderr)
            with warnings.catch_warnings():
                # Never fall back to echoing credentials when no terminal exists.
                warnings.simplefilter("error", getpass.GetPassWarning)
                for name in missing:
                    value = getpass.getpass(f"{name}: ")
                    if not value:
                        raise ValueError(f"No value supplied for {name}; stopped")
                    os.environ[name] = value
                    supplied.append(name)
        return cli_main(argv)
    except (ValueError, OSError, EOFError, getpass.GetPassWarning) as exc:
        message = str(exc) if isinstance(exc, ValueError) else "Unable to read the private environment or secure terminal input; stopped without launching"
        print(f"Error: {message}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    finally:
        for name in supplied:
            os.environ.pop(name, None)


if __name__ == "__main__":
    raise SystemExit(main())
