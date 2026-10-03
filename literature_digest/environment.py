"""Literal private environment data. Never evaluate shell code or expand values."""
from pathlib import Path
import re


def read_environment_file(path, allowed=None):
    """Read data, never source/evaluate shell code. Existing environment wins."""
    path = Path(path)
    if path.stat().st_size > 65536:
        raise ValueError("Environment file is too large (limit: 64 KiB)")
    values = {}
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) or name in values:
            raise ValueError(f"Invalid or duplicate variable at environment file line {number}")
        if value.startswith(("'", '"')):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f"Unclosed quoted value at environment file line {number}")
            value = value[1:-1]
        if "\x00" in value:
            raise ValueError(f"Invalid value at environment file line {number}")
        values[name] = value
    return values if allowed is None else {key: value for key, value in values.items() if key in allowed}

