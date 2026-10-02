#!/usr/bin/env bash
# Cycling Coach - desktop mode launcher (预留接口)
#
# V0.8.2 状态: 占位脚本, 暂未实现
# 未来目标 (V0.9.x): 启动 Tauri / Electron 打包的桌面应用
#
# 当前推荐:
#   - 开发用: ./tools/start.sh  (web 模式, 双击 = 浏览器自动打开)
#   - 未来打包: 走 Tauri/Electron 二进制, 此脚本将被替换为
#     调用 `~/.cycling-coach/cycling-coach-desktop` 或类似命令
#
# Tauri 集成示例 (未来):
#   cd "$(dirname "$BASH_SOURCE[0]")/.."
#   # 后端内嵌 (Tauri 不需要单独起 FastAPI, 直接 import)
#   exec python3 -c "from cycling_coach.desktop import run_app; run_app()"
#
# Electron 集成示例 (未来):
#   exec npx electron .
#
# 为什么不做:
#   - 单人维护, 打包会让迭代速度下降 2-3 倍
#   - web 模式已覆盖 90% 用例
#   - 用户画像: 高级公路车爱好者, 通常能接受装 Node/Python
#
# 何时启用:
#   - 1) 用户开始抱怨 "我不会装 Node"
#   - 2) 需要离线场景 (无网络环境训练)
#   - 3) 需要 OS 集成 (全局快捷键 / 文件拖拽到 app)
# 见 docs/ROADMAP.md (待写) V0.9.x

set -e
echo "⚠️  Desktop mode 尚未实现 (V0.8.2)."
echo "📝  当前请用: ./tools/start.sh (web 模式)"
echo "🔮  计划: V0.9.x 评估 Tauri 实现"
exit 1