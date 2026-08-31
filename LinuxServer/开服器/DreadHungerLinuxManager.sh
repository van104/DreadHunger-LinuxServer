#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

exec python3 "$SCRIPT_DIR/DreadHungerLinuxManager.py" --root "$ROOT" "$@"
