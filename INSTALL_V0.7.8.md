# Cycling Coach V0.7.8 Foundation 1.0 安装指南

> **V0.7.8 是后端 only 更新**, 启动方式跟 V0.7.5.x 一样: 双击 `tools\start.bat` → 浏览器开 `http://localhost:1420`
> **改动**: 4 张新表 + WAL + 索引 + ML 推理基础设施 + chat 持久化 + 性能 + 优雅关闭
> **新增依赖**: `joblib>=1.3,<2.0` + `onnxruntime>=1.16,<2.0` (启动器自动装)

## 方案 A: 已有源码仓库, 拉最新 + 重启

```cmd
cd cycling-coach
git pull origin main
tools\stop.bat
tools\start.bat
```

## 方案 B: 全新安装 (无 git)

1. 下载这个 zip:
   - `cycling-coach-v0.7.8.zip` (162 MB, 含源码 + 训练百科)

2. 解压:
   ```cmd
   :: 用资源管理器右键解压到当前目录
   cd cycling-coach
   tools\start.bat
   ```

3. 浏览器自动开 `http://localhost:1420`

## 方案 C: dev 模式 + AI LLM (可选)

要 AI 教练聊天 / 比赛战术 AI / 训练分析功能, 需要 LLM API key:
1. 复制 `.env.example` 为 `.env`
2. 填 `M3_API_KEY=sk-or-v1-...` (OpenRouter 兼容)
3. 重启 `tools\start.bat`

不填也能用, AI 走 mock 模式返回模板回复.

## 启动时间

- 首次启动: **3-5 分钟** (装依赖 + 编译前端 + 导入 KB)
- 后续启动: **30-60 秒** (依赖已装)
- V0.7.8 启动增量: **+0.5s** (WAL 检测 + 索引检查)

## 端口冲突

跟 V0.7.5.x 一样: 8765 (后端) / 1420 (前端), 见 README "常见问题"

## V0.7.8 新增端点

- 6 个 chat 端点 (`/api/chat/*`)
- 5 个 ML 端点 (`/api/ml/*`)

旧 102 个端点完全兼容, 无破坏性变更。

## 验证

启动后:
```bash
curl http://localhost:8765/api/diagnose
# 期望: {"ok": true, "version": "0.7.8", ...}  (version 字段下一版升 0.7.6)

curl http://localhost:8765/api/chat/sessions
# 期望: []

curl http://localhost:8765/api/ml/models
# 期望: {"ok": true, "models": []}
```

## 故障排除

- **ImportError: joblib** → 装 `pip install joblib`
- **ImportError: onnxruntime** → 装 `pip install onnxruntime` (装失败不影响 mock)
- **journal_mode 不是 wal** → 删 `workspace/cycling_coach.sqlite*` 重建, 或 `sqlite3 workspace/cycling_coach.sqlite "PRAGMA journal_mode=WAL"`
- **杀进程丢 SSE 流** → V0.7.8 已修, 用 `tools\stop.bat` 走 SIGTERM 优雅关闭
