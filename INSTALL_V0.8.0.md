# Cycling Coach V0.8.0 安装指南

> **V0.8.0 重大更新**: 战术规划接 multi-mind + FTP 真模型 + 架构整理
> **新增依赖**: `httpx` (multi-mind HTTP 调) + `joblib` + `onnxruntime` (V0.7.6 已有)
> **新端点**: 0 新增 (只是 `ChatRequest` 加 `mode` 字段)
> **新表**: 0 新增 (V0.7.6 已建 `chat_sessions` / `ml_predictions` 等)
> **新文件**: 7 个 service + 5 layout + 4 store + 思维树 + FTP Card

## 方案 A: 升级 (已有 V0.7.x)

```cmd
cd cycling-coach
git pull origin main
tools\stop.bat
tools\start.bat
```

**首次启动会**：
- 自动 `_auto_migrate` (已有 schema 不动)
- 自动 `Base.metadata.create_all` (新表已建, 不重复建)
- 加载新 service 层 + 7 个公共组件

## 方案 B: 全新安装

下载 `cycling-coach-v0.8.0.zip`, 解压, `tools\start.bat`。

## 方案 C: 接外部仓库 (战术规划 + FTP 真模型)

### 1) 启 multi-mind (战术规划 mode 依赖)

```bash
# 一次性同步 (拉 lixvanran/multi-mind main)
./tools/sync_multi_mind.sh

# 启 multi-mind :8766 (需 OPENROUTER_API_KEY)
./tools/start_multi_mind.sh
```

启动后:
- http://127.0.0.1:8766/health → `{"status": "ok"}`
- http://127.0.0.1:8766/pipelines → 6 个 pipeline (single/multi/adhd_multi/insight_v1/bilateral/insight_v2)

### 2) 拉 ftp-predictor 真模型 (FTP 真预测)

```bash
./tools/sync_ftp_model.sh latest
```

产物:
- `workspace/models/ftp_predictor/latest/best_model.joblib` (429KB GBM)
- `workspace/models/ftp_predictor/latest/conformal_models.joblib` (695KB)
- `workspace/models/ftp_predictor/latest/metadata.json` (训练指标 + 特征定义)

## 端点测试 (curl)

```bash
# 1. 训练答疑 (默认 mode=rag)
curl -X POST http://localhost:8765/api/coach/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"FTP 怎么测?"}]}'
# 预期: 流式 SSE, 含 RAG 引用 [SOURCES]

# 2. 战术规划 (mode=workflow, 需 multi-mind :8766)
curl -X POST http://localhost:8765/api/coach/chat \
  -H "Content-Type: application/json" \
  -d '{"mode":"workflow","messages":[{"role":"user","content":"周末 100km 配速?"}]}'
# 预期: 流式 [NODE] 9 个 + 最终 [DONE] (激进版 + 保守版 + 对比)

# 3. 随便聊聊 (mode=chat, 直 LLM)
curl -X POST http://localhost:8765/api/coach/chat \
  -H "Content-Type: application/json" \
  -d '{"mode":"chat","messages":[{"role":"user","content":"你好"}]}'
# 预期: 流式 SSE, 无 RAG 引用

# 4. FTP 真模型预测 (需 sync 拉 .joblib)
curl -X POST http://localhost:8765/api/ml/predict/ftp -H "Content-Type: application/json" -d '{}'
# 预期: {"ok":true,"predicted_ftp":~250,"lower_80":~243,"upper_80":~257,"model_format":"joblib"}
```

## 故障排除

### 战术规划 mode 不可用 (返 500 / 降级)
- multi-mind 没启: 跑 `tools/start_multi_mind.sh` 或设 `multi_mind_fallback_to_rag=false` 看错误
- OPENROUTER_API_KEY 没设: multi-mind 跑 mock, cycling-coach 也降级

### FTP 预测返 400
- 模型没拉: `tools/sync_ftp_model.sh latest`
- 特征不够: 至少 1 个活动 (samples 完整)
- 20 维特征取不到: 看 `core/ml/feature_pipe.py` Power Zone 1-11 取值逻辑

### 前端 3 tab 不显示
- 检查 `npm run dev` 输出
- `useChatStore` 替换 `useAppStore.chatMessages` 看 `apps/web/src/store/chat.ts`

### `git pull` 后 Python 报 import 错
- 旧进程在跑新代码, 必须 `tools\stop.bat` 后 `tools\start.bat`
- V0.8.0 7 个 service 是新模块, 旧 venv 装的不全: `pip install -e .`

## 升级 V0.7.6 测试

V0.7.6 老 ml 测试 (test_predict_ftp_mock_fallback / test_predictions_list) 在 V0.8.0 标 skip。
原因: V0.8.0 真实集成 ftp-predictor, mock 降级不再是主路径。
新测试: `tests/test_ftp_predictor_v080.py` 13 个 + `tests/test_workflow_v080.py` 22 个。

## 跟 V0.7.x 的兼容性

| 维度 | V0.7.6 / V0.7.8 | V0.8.0 | 兼容性 |
|---|---|---|---|
| API 端点 | 107 / 126 | 107 / 126 (加 mode 字段) | ✓ 向后兼容 |
| DB 表 | 16 | 16 | ✓ |
| 数据 | 用户数据 | 不动 | ✓ |
| .env 变量 | M3_API_KEY 等 | 加 multi_mind_url 等 (有默认值) | ✓ |
| FTP 预测 | Mock 兜底 | 真模型 / Mock 兜底 | ✓ 平滑过渡 |
| Chat | 单 mode (rag) | 3 mode (rag/workflow/chat), 默认 rag | ✓ |
| 前端路由 | 17 页面 | 17 页面 + 5 layout + 路由分组 | ✓ HashRouter 兜底旧 URL |
