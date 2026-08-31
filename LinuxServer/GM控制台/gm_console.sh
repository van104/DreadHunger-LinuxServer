#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DEFAULT_ROOT="/www/wwwroot/Dread Hunger/LinuxServer"

if [ -d "$DEFAULT_ROOT" ]; then
    ROOT="$DEFAULT_ROOT"
else
    ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
fi

exec python3 "$SCRIPT_DIR/gm_console.py" --root "$ROOT" "$@"
