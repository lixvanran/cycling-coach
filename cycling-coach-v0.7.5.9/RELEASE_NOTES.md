# Cycling Coach V0.7.5.9 - 比赛战术规划 (后端 + AI)

> **发布日期**: 2026-08-31

## V0.7.5.9 vs V0.7.5.8

### 新功能: 比赛战术规划 (Race Tactics Planning)

**场景**: 业余车手备战具体比赛, 跟教练 (AI) 多轮讨论战术, 可上传路书 (PDF/PNG/JPG)

**借鉴**: TrainingPeaks Race Plan / WKO5 Race Day / GoldenCheetah 比赛计划

### 数据模型 (3 表)
- `race_tactics_sessions` — 战术会话 (比赛信息 + 状态)
- `race_tactics_messages` — 对话消息 (user/assistant + RAG 引用)
- `race_tactics_attachments` — 路书附件 (含 OCR 提取文本)

### 端点 (10 个, 全新增)
- `GET    /api/race-tactics/sessions` 所有会话
- `POST   /api/race-tactics/sessions` 创建
- `GET    /api/race-tactics/sessions/{id}` 详情 (含消息 + 附件)
- `PATCH  /api/race-tactics/sessions/{id}` 更新
- `DELETE /api/race-tactics/sessions/{id}` 删除
- `POST   /api/race-tactics/sessions/{id}/upload` 上传路书 (PDF 解析文字)
- `DELETE /api/race-tactics/sessions/{id}/attachments/{att_id}` 删附件
- `GET    /api/race-tactics/attachments/{att_id}/download` 下载
- `POST   /api/race-tactics/sessions/{id}/messages` 发消息 (SSE 流式)
- `POST   /api/race-tactics/sessions/{id}/suggest` AI 自动生成战术

### AI 集成
- System prompt: 比赛信息 + 运动员画像 (FTP/max_hr/weight_kg) + 路书 OCR + KB 检索
- 借鉴 潘震训练百科 "竞技百科" 分类 (3 篇) + "比赛路线看什么" + "比赛前都要做什么"
- RAG top-K=4-5 chunks, 引用时标注来源路径
- mock 模式 (无 M3_API_KEY) 用 KB 拼回答, 真 LLM 模式自动 fallback

### 安全 / 健壮性
- [x] 路径遍历修复: `Path(filename).name` + 解析后断言
- [x] 20MB 上传大小限制
- [x] 错误外泄防护: `data: [ERROR] AI 响应失败` 不显示 ORM 堆栈
- [x] SSE 流式 (`text/event-stream`), 客户端可中断

### 沙箱验证
- TSC: 0 错 (无前端改动)
- pytest: 41 passed
- 后端冒烟: 业务端点 + 10 新端点全 200
- 流式消息: SSE chunk 正常 yield
- 端点总数: 88+10 = 98 paths, 105+10 = 115 method (V0.7.5.9: 98 / 115)

### V0.7.5.10 (下一版)
- 前端 `RaceTacticsPage` (待写)
- Sidebar 加入口 (Trophy 图标)
- 列表 + 详情 (左侧路书 + 信息, 右侧聊天)
- 上传 UI (拖拽 PDF/PNG)
- 集成 chat 流式 + 计时
