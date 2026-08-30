# Cycling Coach · Windows 桌面端打包指南

> 版本: v0.5.3
> 目标: 在 Windows 10/11 上跑一行命令, 产出 `CyclingCoach-Setup-0.5.3-x64.exe`
> 用户安装后: 开始菜单 + 桌面 + 任务栏都有快捷方式, 双击启动

---

## 1. 概览

Cycling Coach 桌面端由两部分组成:

| 组件 | 技术 | 体积 | 作用 |
|------|------|------|------|
| Electron 壳 | Electron 26 | ~80 MB | 窗口、菜单、托盘、NSIS 安装器 |
| 后端 | Python 3.11 + FastAPI (PyInstaller 打包) | ~90 MB | API + KB 搜索 + 训练分析 |
| 前端 | React 18 + Vite 5 | ~3 MB | UI |
| **总安装体积** | | **~170 MB** | KB 不打包, 首次启动解压到 `%APPDATA%` |

**为什么不打包 KB 进安装包?**
KB 训练百科有 159 MB / 359 文档, 打包进 NSIS 会让 Setup.exe 巨大且更新不便.
采用 **首次启动解压**: 资源目录 `resources\kb_source\` 在 `app.asar` 旁边, 启动时
检测 `%APPDATA%\CyclingCoach\kb\extracted\markdown\` 不存在就 copy 一份, 之后直接读.

---

## 2. 前置环境 (一次性)

| 工具 | 版本 | 安装 |
|------|------|------|
| Python | 3.11+ | https://www.python.org/downloads/ (勾 "Add to PATH") |
| Node.js | 20+ | https://nodejs.org/ (LTS) |
| pnpm | 8+ | `npm install -g pnpm` |
| PyInstaller | 6+ | `pip install pyinstaller` |
| Git | 任意 | (可选) 拉代码 |

**磁盘空间**: 项目 ~2 GB, 构建后 dist ~500 MB, 安装后约 250 MB.

**Windows 平台**: Win10 1809+ 或 Win11. 64-bit.

---

## 3. 一键打包

```bat
git clone https://github.com/<your-fork>/cycling-coach.git
cd cycling-coach
tools\build-windows-installer.bat
```

整个流程大约 8-12 分钟 (主要花在 PyInstaller 上).

完成后:

```
apps\desktop\dist-electron\
  └─ CyclingCoach-Setup-0.5.3-x64.exe   <- 双击这个给用户装
```

脚本会:
1. 检查 Python / Node / pnpm / pyinstaller 是否就绪
2. 跑 `pnpm install` (monorepo 根, 装所有 Electron 依赖)
3. 自动创建 `.venv` 并装 Python 依赖
4. `pyinstaller` 打包后端为 `dist\CyclingCoach-backend-dist\CyclingCoach-backend.exe`
5. `pnpm build` 构建前端到 `apps\web\dist\`
6. 把后端 binary 复制到 `apps\desktop\build-resources\backend\`
7. `electron-builder --win nsis` 产出 NSIS Setup.exe
8. 自动打开输出目录

---

## 4. 安装效果

双击 `CyclingCoach-Setup-0.5.3-x64.exe` 后, NSIS 走标准流程:

- 选安装目录 (默认 `%LOCALAPPDATA%\Programs\CyclingCoach\`, 建议默认)
- 勾"创建桌面快捷方式" + "创建开始菜单快捷方式" (默认勾)
- 安装完成后, 在 **开始菜单** + **桌面** 都能看到 `Cycling Coach` 图标
- 双击启动, 单 instance 锁 (再点不会开第二个窗口)
- 关闭主窗口 → 缩到系统托盘 (气球通知 "仍在后台运行")
- 托盘右键 → 打开主窗口 / 打开数据目录 / 退出
- 任务栏图标右键可固定 (pin to taskbar)

**用户数据目录** (`%APPDATA%\CyclingCoach\`):
```
CyclingCoach\
  ├─ cycling_coach.db          <- SQLite (活动/计划/PMC/...)
  ├─ kb\extracted\             <- 训练百科 (首次启动解压)
  │  ├─ markdown\              <- 359 .md
  │  └─ attachments\           <- 252 文件
  ├─ logs\                     <- 应用日志
  │  ├─ electron.log
  │  └─ backend.log
  └─ cache\                    <- 缓存
```

**卸载**: 设置 → 应用 → 卸载. 默认**保留**用户数据, 选 "同时删除数据" 才清空.


## 4.5 卸载

### 生产用户 (装过 Setup.exe)

**方法 1: 开始菜单**
- 开始菜单 → 找到 `Cycling Coach` 文件夹 → 里面有个 "卸载 Cycling Coach" 快捷方式 → 双击

**方法 2: 设置**
- Windows 设置 → 应用 → 安装的应用 → 找 `Cycling Coach` → 卸载

**方法 3: 控制面板**
- 控制面板 → 程序与功能 → 找 `Cycling Coach` → 右键卸载

NSIS uninstaller 流程:
1. 确认卸载目录
2. 杀掉 `CyclingCoach.exe` + `CyclingCoach-backend.exe` 进程
3. 删 `%LOCALAPPDATA%\Programs\CyclingCoach\` (~250 MB 安装文件)
4. 删桌面 / 开始菜单快捷方式
5. **默认保留** `%APPDATA%\CyclingCoach\` (用户数据 + KB)
6. 询问 "同时删除数据?" → 选是才彻底清

> 用户数据 (活动/计划/PMC) 在 SQLite, 删了不可恢复.
> KB 训练百科 (159 MB) 是从 `resources\kb_source\` 解压的副本, 删了下次启动会重新解压.
> 建议: 想干净重装 → 选"是"删数据. 想保留训练历史 → 选"否".

### 开发用户 (跑过 dev 模式)

dev 模式 (没装过 Setup.exe) 用 `tools\uninstall.bat`:

```bat
:: 1. 清 build artifacts, 保留用户数据 + .venv
tools\uninstall.bat

:: 2. 全清 (含 .venv, workspace)
tools\uninstall.bat --purge-data

:: 3. 清 build, 保 .venv (快速重建用)
tools\uninstall.bat --keep-venv
```

会清掉:
- 进程 (`CyclingCoach.exe` / `CyclingCoach-backend.exe` / `electron.exe` / `node.exe`)
- `.venv\` (可选, `--keep-venv` 跳过)
- `dist\` `build\` (PyInstaller 临时)
- `cycling_coach\static\` (PyInstaller 软链目标)
- `apps\web\dist\` (前端 Vite build 产物)
- `apps\web\node_modules\`
- `apps\desktop\node_modules\`
- `apps\desktop\dist-electron\` (Setup.exe)
- `apps\desktop\build-resources\backend\` (后端 binary)
- 沙盒残留: `diagnose.txt` `cc-desktop-debug.log` `cycling-coach-*.zip`
- `--purge-data` 时: `workspace\` (用户数据)

> **不**会动:
> - `kb_source\` (训练百科源, 159 MB, 重新 build 要用)
> - `docs\` `apps\web\src\` `cycling_coach\` (源码)
> - `.env` / `.env.example` (配置)

---

## 5. 常见问题

### 5.1 PyInstaller OOM / 卡住

PyInstaller 内存峰值 ~2 GB, 如果机器 < 8 GB RAM, 走 `--onedir` 而不是 `--onefile`:
spec 默认就是 `EXE + COLLECT` (onedir), 没问题.

### 5.2 启动时弹 "后端启动超时"

`127.0.0.1:8765` 被占用. 检查:
```bat
netstat -ano | findstr :8765
taskkill /F /PID <pid>
```

### 5.3 首次启动 KB 没自动导入

看 `%APPDATA%\CyclingCoach\logs\backend.log`, 搜索 `kb`. 常见:
- KB 源 `resources\kb_source\` 不存在 → 重新跑 `tools\build-windows-installer.bat`
- 磁盘空间不够 → KB 159 MB, 至少留 500 MB

### 5.4 杀毒软件报毒

PyInstaller 单文件 exe + 未知发布者 → 部分杀软 (360 / 火绒) 会拦截.
解决方案:
- 走 code signing (暂未实施, 需买 EV 证书)
- 用户手动添加信任
- 改用 `--onedir` 模式 (spec 已是) + 7z 自解压

### 5.5 跨平台编译

当前 spec **只能在 Windows 上跑** (因为后端 .exe = Windows PE).
Linux / macOS 编译后端没问题, 但 Electron NSIS installer 必须 Windows 平台 (或 Linux 装 wine + makensis).

---

## 6. 进阶: 只 build 某一部分

### 只 build 后端 (调试)
```bat
.venv\Scripts\activate
pyinstaller apps\desktop\build\pyinstaller-backend.spec --noconfirm --clean
```
产物: `dist\CyclingCoach-backend-dist\CyclingCoach-backend.exe`
直接双击或 `cd dist\CyclingCoach-backend-dist && CyclingCoach-backend.exe` 跑 (默认 listen 8765).

### 只 build 前端
```bat
cd apps\web
pnpm build
```
产物: `apps\web\dist\` (HTML + JS + CSS)

### 只 build Electron
```bat
cd apps\desktop
npx electron-builder --win nsis --x64
```
前置: `apps\desktop\build-resources\backend\CyclingCoach-backend.exe` 必须存在.

---

## 7. 文件结构 (与 build 相关的)

```
cycling-coach/
├── apps/
│   ├── web/                    <- Vite 前端源码
│   │   ├── dist/               <- (build 产物, 不入库)
│   │   └── package.json
│   └── desktop/                <- Electron 壳
│       ├── main.cjs            <- 主进程 (lifecycle + 后端 spawn)
│       ├── preload.cjs         <- IPC 桥
│       ├── package.json        <- electron-builder NSIS config
│       ├── build/              <- 图标
│       │   ├── installerIcon.svg
│       │   ├── icon.ico
│       │   ├── icon.png
│       │   └── icon.icns
│       ├── build-resources/    <- (build 时填入)
│       │   └── backend/
│       │       └── CyclingCoach-backend.exe
│       ├── dist-electron/      <- (build 产物, 不入库)
│       │   └── CyclingCoach-Setup-0.5.3-x64.exe
│       └── node_modules/       <- (npm install 后)
├── cycling_coach/              <- Python 后端源码
│   ├── __main__.py             <- 入口 (uvicorn cycling_coach.api.main:app)
│   ├── api/                    <- FastAPI
│   ├── core/                   <- KB / 分析 / AI
│   └── ...
├── desktop/
│   └── pyinstaller-backend.spec  <- PyInstaller 配置
├── kb_source/                  <- (可选) 训练百科
│   ├── markdown/
│   └── attachments/
└── tools/
    └── build-windows-installer.bat
```

---

## 8. 升级流程 (后续版本)

1. 改 `apps/desktop/package.json` 的 `version` + 源码里的版本号
2. 改 `apps/desktop/build/pyinstaller-backend.spec` 注释里的版本
3. 跑 `tools\build-windows-installer.bat`
4. 测试 Setup.exe
5. 发到 GitHub Releases (或用户分发)

---

**Built with ❤️ for road cyclists. 🚴‍♂️**
