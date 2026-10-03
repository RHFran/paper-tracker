#!/bin/sh
# Example only: customize absolute paths and keep the environment file private.
set -eu
umask 077
cd /absolute/path/smart-paper-tracker
# Application parses the file as literal data; never shell-source wizard output.
exec .venv/bin/python -m literature_digest --env-file /absolute/private/path/.env --config /absolute/private/path/config.json tick --send
