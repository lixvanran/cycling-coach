# Cycling Coach V0.7.5.6 安装指南

> **无桌面安装包**: V0.7.5.6 桌面应用仍暂停 (V0.5.3 闪退, 暂用 dev 模式 + 浏览器)
> **本文教你用 dev 模式跑 V0.7.5.6**: 双击 `tools\start.bat` → 浏览器开 `http://localhost:1420`

---

## 方案 A: 已有源码仓库, 拉最新 + 重启

```cmd
cd cycling-coach
git pull origin main    :: 或 git fetch + git reset --hard origin/main
tools\stop.bat          :: 关掉旧进程
tools\start.bat         :: 启动 V0.7.5.6
```

## 方案 B: 全新安装 (无 git)

1. 下载这 2 个 zip:
   - `cycling-coach-v0.7.5.5-source.zip` (5.1 MB) — 源码
   - `cycling-coach-v0.7.5.5-kb.zip` (156 MB) — 训练百科 (受限许可)

2. 解压 source zip, 会得到 `cycling-coach-v0.7.2/` 目录

3. 复制 kb zip **进** source 目录, 解压覆盖 `kb_source/`:
   ```cmd
   cd cycling-coach-v0.7.2
   :: 把 cycling-coach-v0.7.5.5-kb.zip 放当前目录
   :: 用资源管理器右键解压到当前目录, 合并 kb_source/
   tools\start.bat
   ```

4. 浏览器自动开 `http://localhost:1420`

## 方案 C: dev 模式 + AI LLM (可选)

要 AI 教练聊天功能, 需要 LLM API key:
1. 复制 `.env.example` 为 `.env`
2. 填 `M3_API_KEY=sk-or-v1-...` (OpenRouter 兼容)
3. 重启 `tools\start.bat`

不填也能用, AI 走 mock 模式返回模板回复.

## 启动时间

- 首次启动: **3-5 分钟** (装依赖 + 编译前端 + 导入 KB)
- 后续启动: **30-60 秒** (依赖已装)

## 端口冲突

- 后端 8765 / 前端 1420 — `tools\stop.bat` 可关
- Windows 检查: `netstat -ano | findstr :8765`

## 桌面应用 (.exe) 状态

**V0.5.3 桌面端闪退, 搁置中**. 不打 NSIS Setup.exe.
原因: Electron 启动后端 + 前端异步有兼容问题, 闪退.

**当前推荐**: dev 模式 (本指南).

## 知识库 License

- 软件代码: MIT
- **训练百科** (`kb_source/`): Restricted by **潘震(公路车教练)** — 详见 `kb_source/LICENSE`

