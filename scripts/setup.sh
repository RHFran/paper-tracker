#!/usr/bin/env bash
# Creates only a local virtual environment/config/preview; no sudo or service.
set -euo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  printf '%s\n' 'Python 3.11+ is required. Install it from python.org or your OS package manager, then retry.' >&2
  exit 1
fi
exec "$PYTHON" "$ROOT/scripts/setup.py" "$@"
