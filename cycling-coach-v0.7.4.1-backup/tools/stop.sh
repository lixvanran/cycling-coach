#!/usr/bin/env bash
# Cycling Coach - dev mode stopper (macOS / Linux)
# 用法: ./tools/stop.sh [args...]
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
export PYTHONUTF8="${PYTHONUTF8:-1}"
exec python3 tools/stop.py "$@"
