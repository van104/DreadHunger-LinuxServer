#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

python3 -m PyInstaller --onefile --clean --noconfirm \
  --name DreadHungerLinuxManager \
  --distpath "$SCRIPT_DIR" \
  --workpath "$SCRIPT_DIR/.pyinstaller-build" \
  "$SCRIPT_DIR/DreadHungerLinuxManager.py"

echo "Built: $SCRIPT_DIR/DreadHungerLinuxManager"
