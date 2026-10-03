#!/bin/sh
# Example only: customize absolute paths and keep the environment file private.
set -eu
umask 077
set -a
. /absolute/private/path/literature-digest.env
set +a
cd /absolute/path/paper-tracker
exec .venv/bin/python -m literature_digest --config /absolute/private/path/config.json tick --send
