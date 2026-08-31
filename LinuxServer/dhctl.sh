#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON="$SCRIPT_DIR/.venv/bin/python3"

if [ ! -x "$PYTHON" ]; then
    echo "错误：尚未安装运行环境，请先执行 ./install.sh" >&2
    exit 1
fi

exec "$PYTHON" "$SCRIPT_DIR/dhctl.py" "${1:-status}"
