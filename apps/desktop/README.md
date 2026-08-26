# Cycling Coach Desktop (Electron)

> ⚠️ **状态: 预留 (Reserved) — V0.5.3 起暂停维护**
>
> 桌面应用代码保留作为未来参考, **当前推荐使用 dev 模式 (一键启动 + 浏览器)**:
> - Windows: `tools\start.bat`
> - macOS / Linux: `./tools/start.sh`
> - 然后浏览器访问 `http://localhost:1420`
>
> 桌面应用遇到技术问题 (PyInstaller 跨平台兼容性 / Electron 配置 / 安装器签名等),
> 短期内不再投入. 等技术方案更成熟时再重启.

## 历史 (V0.5.3)

V0.5.3 曾尝试用 **Electron + PyInstaller + electron-builder NSIS** 出一键 Setup.exe.
代码完整, 但 Windows 装机存在稳定性问题 (闪退 / 杀软拦截 / 端口冲突等),
决定先转回 dev 模式, 桌面代码保留作为后续基础.

## 目录

```
apps/desktop/                  <- 预留代码, 当前不打包
├── main.cjs                   Electron 主进程
├── preload.cjs                IPC 桥
├── package.json               electron-builder NSIS config
├── build/                     构建资源 (spec, icon, svg)
└── ...
```

## 卸载

桌面应用代码不影响 dev 模式. 如果你想清掉桌面代码:
```bash
# (可选) 仅清 build artifacts, 留代码
tools\uninstall.bat

# (可选) 完全清 build artifacts
rm -rf apps/desktop/dist-electron apps/desktop/build-resources
```

## dev 模式一键启动

```bat
:: Windows
tools\start.bat

:: macOS / Linux
./tools/start.sh
```

会自动:
- 装 Python venv + 依赖
- 装 Node 依赖
- 启动 Vite (前端 HMR, 端口 1420)
- 启动 FastAPI (后端, 端口 8765)
- 自动打开浏览器 `http://localhost:1420`

停止: `tools\stop.bat` (Windows) / `./tools/stop.sh` (Unix)
