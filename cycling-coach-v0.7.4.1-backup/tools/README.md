# tools/ — 工具脚本

所有工具都从这里出. 命名统一英文 + 直白.

## 一键启动 / 停止 / 诊断 / 卸载

| 脚本 | 平台 | 作用 |
|------|------|------|
| `start.bat` / `start.sh` | Windows / Unix | 启动 dev 模式 (Vite + FastAPI) |
| `stop.bat` / `stop.sh` | Windows / Unix | 停止 dev 模式 (kill 进程) |
| `diagnose.bat` (Unix: `python tools/diagnose.py`) | Windows | 诊断环境问题, 输出日志 |
| `uninstall.bat` / `uninstall.sh` | Windows / Unix | 一键卸载, 清 build artifacts |
| `build-windows-installer.bat` | Windows | 打 Setup.exe (PyInstaller + electron-builder NSIS) |

## Python 底层 (给 .bat 调)

| Python | 作用 |
|--------|------|
| `start.py` | dev 模式: 自动装 venv / 镜像 / 跨平台 shim / 端口兜底 |
| `stop.py` | dev 模式: 杀进程, 释放端口 |
| `diagnose.py` | 输出系统环境 / Python / Node / pnpm / 端口 / 依赖报告 |

## 用法示例

```bash
# Windows
tools\start.bat                    # 启动
tools\stop.bat                     # 停止
tools\diagnose.bat                 # 诊断
tools\uninstall.bat --purge-data   # 全清 (含用户数据)
tools\build-windows-installer.bat  # 打 Setup.exe (Windows 用户)

# macOS / Linux
./tools/start.sh
./tools/stop.sh
./tools/uninstall.sh --keep-venv
```

## 不在 tools/ 里的脚本

- `apps/desktop/build/pyinstaller-backend.spec` — PyInstaller spec (放 build artifacts 旁边)
- `apps/desktop/build/installerIcon.svg` — 图标

## 旧文件位置 (V0.5.3 之前)

`tools/platform/windows/{start,stop,diagnose}.bat` 已删,
统一挪到 `tools/` 根 + 英文命名 (历史曾用中文文件名 `启动.bat` / `停止.bat` / `诊断.bat`,
现统一为 `start.bat` / `stop.bat` / `diagnose.bat`).
