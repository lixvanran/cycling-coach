#!/usr/bin/env bash
# Cycling Coach - 一键卸载 (macOS / Linux dev 模式清理)
#
# 选项:
#   --purge-data   连用户数据一并删除
#   --keep-venv    保留 .venv
#
# 用法:
#   ./tools/uninstall.sh
#   ./tools/uninstall.sh --purge-data
#   ./tools/uninstall.sh --keep-venv
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

PURGE_DATA=0
KEEP_VENV=0
for arg in "$@"; do
  case "$arg" in
    --purge-data) PURGE_DATA=1 ;;
    --keep-venv)  KEEP_VENV=1 ;;
  esac
done

echo
echo "============================================================"
echo " Cycling Coach - 一键卸载"
echo " Root: $ROOT_DIR"
echo "============================================================"
echo
echo "  即将清理以下内容:"
[ "$KEEP_VENV" -eq 0 ] && echo "   - .venv/                  (Python 虚拟环境, ~200 MB)"
echo "   - apps/desktop/dist-electron/   (Setup.exe 构建产物)"
echo "   - dist/                        (PyInstaller 临时输出)"
echo "   - build/                       (PyInstaller 临时输出)"
echo "   - cycling_coach/static/        (前端 build 软链)"
echo "   - apps/web/dist/               (前端 build 产物)"
echo "   - apps/web/node_modules/"
echo "   - apps/desktop/node_modules/"
if [ "$PURGE_DATA" -eq 1 ]; then
  echo
  echo "   !! 警告 --purge-data !!:"
  echo "   - workspace/                  (用户数据: 活动/计划/PMC)"
  echo "   - workspace/input/            (FIT 原始文件)"
  echo "   - workspace/.logs/            (日志)"
fi
echo
read -p "确认卸载? (y/N): " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
  echo "已取消."
  exit 0
fi

echo
echo "清理中..."

# 1. 杀进程
echo "  - 杀 cycling_coach 相关进程..."
pkill -f "CyclingCoach" 2>/dev/null || true
pkill -f "electron.*cycling" 2>/dev/null || true
pkill -f "uvicorn.*cycling_coach" 2>/dev/null || true

# 2. 删 venv
if [ "$KEEP_VENV" -eq 0 ] && [ -d .venv ]; then
  echo "  - 删除 .venv ..."
  rm -rf .venv
fi

# 3. 删 build artifacts
for d in dist build; do
  if [ -d "$d" ]; then
    echo "  - 删除 $d ..."
    rm -rf "$d"
  fi
done
[ -d cycling_coach/static ] && rm -rf cycling_coach/static && echo "  - 删除 cycling_coach/static"
[ -d apps/web/dist ] && rm -rf apps/web/dist && echo "  - 删除 apps/web/dist"
[ -d apps/web/node_modules ] && rm -rf apps/web/node_modules && echo "  - 删除 apps/web/node_modules"
[ -d apps/desktop/dist-electron ] && rm -rf apps/desktop/dist-electron && echo "  - 删除 apps/desktop/dist-electron"
[ -d apps/desktop/node_modules ] && rm -rf apps/desktop/node_modules && echo "  - 删除 apps/desktop/node_modules"
[ -d apps/desktop/build-resources/backend ] && rm -rf apps/desktop/build-resources/backend && echo "  - 删除 apps/desktop/build-resources/backend"

# 4. 沙盒残留
[ -f cc-desktop-debug.log ] && rm cc-desktop-debug.log && echo "  - 删除 cc-desktop-debug.log"
[ -f diagnose.txt ] && rm diagnose.txt && echo "  - 删除 diagnose.txt"
rm -f cycling-coach-*.zip cycling-coach-*.tar.gz 2>/dev/null && echo "  - 删除 cycling-coach-*.{zip,tar.gz}"

# 5. 用户数据
if [ "$PURGE_DATA" -eq 1 ] && [ -d workspace ]; then
  echo "  - 删除 workspace (用户数据) ..."
  rm -rf workspace
else
  echo "  - 保留 workspace (用户数据: workspace/cycling_coach.sqlite)"
fi

echo
echo "============================================================"
echo " 卸载完成!"
if [ "$PURGE_DATA" -eq 1 ]; then
  echo " 用户数据已删除."
else
  echo " 用户数据保留在: $ROOT_DIR/workspace"
  echo " 彻底清:  ./tools/uninstall.sh --purge-data"
fi
echo "============================================================"
