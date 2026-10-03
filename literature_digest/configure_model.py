"""Interactive provider/model configuration; secrets never enter CLI arguments."""
from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit
import warnings

from .config import load_configs
from .environment import read_environment_file
from .locking import exclusive_file_lock

# Base URLs verified against provider documentation; model IDs stay user-selected.
PROVIDERS = {
    "deepseek": ("DeepSeek", "https://api.deepseek.com"),
    "qwen": ("Qwen / Alibaba Cloud, Beijing", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    "moonshot": ("Moonshot / Kimi, China", "https://api.moonshot.cn/v1"),
    "openai": ("OpenAI", "https://api.openai.com/v1"),
    "custom": ("Custom OpenAI-compatible HTTPS service", ""),
}


def _text(value, label, maximum=4096):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or value.splitlines() != [value] or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"{label} must be nonempty single-line text without control characters")
    return value


def _private_atomic_write(path, text):
    descriptor, temporary = tempfile.mkstemp(prefix=".paper-tracker-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def configure_model(args, input_fn=None, secret_fn=None, output_fn=print):
    """Configure one subscription. Provider calls and SMTP are never performed."""
    input_fn = input_fn or input
    secret_fn = secret_fn or getpass.getpass
    config_path = Path(args.config).absolute()
    if config_path.is_symlink() or config_path.name.endswith(".example.json"):
        raise ValueError("Choose a private regular config file, not a symlink or bundled example; run init or copy the example first")
    original_config = config_path.read_bytes()
    raw = json.loads(original_config)
    configs = load_configs(str(config_path))
    selected = [c for c in configs if not args.profile or c["profile_id"] == args.profile]
    if len(selected) != 1 or "profiles" in raw and not args.profile:
        raise ValueError("Choose exactly one subscription with --profile for model configuration")
    selected = selected[0]
    target = raw if "profiles" not in raw else next(p for p in raw["profiles"] if p["id"] == args.profile)
    if selected["llm"]["enabled"] and not args.replace:
        raise ValueError("This subscription already has an enabled model. Use --replace only if you intend to change it")
    secrets_path = Path(args.secrets_file or ".env")
    if not secrets_path.is_absolute():
        secrets_path = config_path.parent / secrets_path
    secrets_path = secrets_path.absolute()
    if secrets_path.name == ".env.example" or not (secrets_path.name == ".env" or secrets_path.name.startswith(".env.")) or secrets_path.is_symlink():
        raise ValueError("Secrets filename must be .env or .env.<private-name>, never .env.example or a symlink")
    original_secrets = secrets_path.read_bytes() if secrets_path.exists() else None
    existing = read_environment_file(secrets_path) if original_secrets is not None else {}

    output_fn("This wizard selects the standalone API workflow. Full Codex/Claude/host agents use workflow.mode=agent and agent.backend instead. API token usage may incur provider charges, depending on model, paper count and evidence length. No model call is made by this wizard or offline preview.")
    output_fn("Super Paper radar uses non-streaming OpenAI-compatible Chat Completions with JSON-object output. Select a model that supports these options; provider presets are not live-tested compatibility guarantees.")
    names = list(PROVIDERS)
    for number, provider in enumerate(names, 1):
        output_fn(f"{number}. {PROVIDERS[provider][0]} ({provider})")
    provider = input_fn("Provider name or number [deepseek]: ").strip().lower() or "deepseek"
    if provider.isdigit() and 1 <= int(provider) <= len(names):
        provider = names[int(provider) - 1]
    if provider not in PROVIDERS:
        raise ValueError("Unknown provider; choose a listed name or custom")
    default_base = PROVIDERS[provider][1]
    base = _text(input_fn(f"HTTPS base URL [{default_base or 'required'}]: ").strip() or default_base, "Base URL")
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or base.rstrip("/").endswith("/chat/completions"):
        raise ValueError("Enter an HTTPS base URL without credentials, query, fragment or /chat/completions suffix")
    model = _text(input_fn("Model ID from your provider console (required): ").strip(), "Model ID", 200)
    default_slot = re.sub(r"[^A-Za-z0-9_]", "_", selected["profile_id"]).upper()
    slot = input_fn(f"Local model/key slot [{default_slot}]: ").strip().upper() or default_slot
    if not re.fullmatch(r"[A-Z0-9_]{1,64}", slot):
        raise ValueError("Slot must contain 1-64 letters, digits or underscores")
    prefix = "PAPER_TRACKER_" + slot
    references = {"base_url_env": prefix + "_BASE_URL", "api_key_env": prefix + "_API_KEY", "model_env": prefix + "_MODEL"}
    reserved = set(references.values())
    if reserved & set(existing) and not args.replace:
        raise ValueError("That local model/key slot already exists. Choose a new slot, or use --replace explicitly")
    others = [c for c in configs if c["profile_id"] != selected["profile_id"]]
    if any(reserved & {value for key, value in c["llm"].items() if key.endswith("_env")} for c in others):
        raise ValueError("That model/key slot is used by another subscription. Choose a distinct slot to avoid changing its provider")

    output_fn("API key entry is hidden. Never paste a key into an agent chat, command argument, screenshot or log.")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            key = _text(secret_fn("API key (hidden): "), "API key")
        except getpass.GetPassWarning:
            raise ValueError("Secure terminal input is unavailable. Run configure-model yourself in a local interactive terminal") from None
    output_fn(f"Will save the key in {secrets_path} and enable this subscription's model in {config_path}. Existing unrelated keys and subscriptions are preserved. Mail remains unchanged; no scheduler is installed.")
    output_fn("The secret file is local plaintext. On POSIX it is owner-only (0600); on Windows use a private user directory and verify its Windows access permissions.")
    if input_fn("Type yes to save locally, or anything else to cancel: ").strip().lower() != "yes":
        return {"status": "cancelled", "saved": False, "network_used": False, "mail_sent": False}

    values = {references["base_url_env"]: base, references["api_key_env"]: key, references["model_env"]: model}
    secret_lines = (original_secrets.decode("utf-8-sig").splitlines() if original_secrets is not None else ["# Private Super Paper radar provider values. Never commit or share.", "# Literal KEY='value' data; no shell expansion."])
    kept = [line for line in secret_lines if line.strip().partition("=")[0].strip() not in reserved]
    # Quotes are literal outer delimiters; the parser never interprets content.
    secret_text = "\n".join(kept + [f"{name}='{value}'" for name, value in values.items()]) + "\n"
    target["workflow"] = {"mode": "standalone"}
    target["llm"] = {**target.get("llm", {}), "enabled": True, "backend": "api", **references}
    config_text = json.dumps(raw, ensure_ascii=False, indent=2) + "\n"
    secrets_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with exclusive_file_lock(str(config_path) + ".setup.lock"), exclusive_file_lock(str(secrets_path) + ".setup.lock"):
        current_secrets = secrets_path.read_bytes() if secrets_path.exists() else None
        if config_path.read_bytes() != original_config or current_secrets != original_secrets:
            raise ValueError("Configuration changed while the wizard was open. Nothing was saved; run it again")
        _private_atomic_write(secrets_path, secret_text)
        try:
            _private_atomic_write(config_path, config_text)
        except OSError:
            # Avoid silently leaving a new credential behind if config saving fails.
            if original_secrets is None:
                secrets_path.unlink()
            else:
                _private_atomic_write(secrets_path, original_secrets.decode("utf-8-sig"))
            raise
    return {"status": "model_configured", "profile_id": selected["profile_id"], "provider": provider,
            "config_path": str(config_path), "secrets_path": str(secrets_path), "secret_saved": True,
            "network_used": False, "mail_sent": False, "next": "Use the launcher with --env-file <secrets-path> validate, then explicitly run a live dry-run (API token charges may apply)."}
