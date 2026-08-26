#!/usr/bin/env bash
# Cycling Coach - dev mode launcher (macOS / Linux)
# 用法: ./tools/start.sh [args...]
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
export PYTHONUTF8="${PYTHONUTF8:-1}"
mkdir -p workspace/.logs
exec python3 tools/start.py "$@"
