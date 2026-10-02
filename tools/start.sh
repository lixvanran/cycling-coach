#!/usr/bin/env bash
# Cycling Coach - dev mode launcher (macOS / Linux)
# 用法: ./tools/start.sh [args...]
#
# 启动后: 后端 :8765 + 前端 :1420 (Vite dev server)
# 双击此脚本 = 自动起后端 + 浏览器
#
# ─────────── 未来桌面入口 ───────────
# 未来 (V0.9.x) 上 Tauri/Electron 时, 此脚本继续作为 dev 入口;
# 打包后的二进制会走 ./tools/start-desktop.sh (当前是占位, 未来实现)
# 详见 apps/web/src/lib/platform.ts 的 PlatformInfo / Capabilities 抽象
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
export PYTHONUTF8="${PYTHONUTF8:-1}"
mkdir -p workspace/.logs
exec python3 tools/start.py "$@"
