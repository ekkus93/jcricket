#!/bin/sh
set -eu
credentials_file="${SECOND_BRAIN_CREDENTIALS_FILE:-$HOME/.config/second-brain/credentials.env}"
set -a
. "$credentials_file"
set +a
exec uv run second-brain --config "${SECOND_BRAIN_CONFIG:-config.yaml}" serve
