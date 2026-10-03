#!/usr/bin/env bash
set -euo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  printf '%s\n' 'Run bash scripts/setup.sh first (Python 3.11+ required).' >&2
  exit 1
fi
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/launch.py" "$@"
