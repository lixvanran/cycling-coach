# Cycling Coach V0.7.5.10 - 比赛战术规划 (前端 + 完整功能)

> **发布日期**: 2026-08-31

## V0.7.5.10 vs V0.7.5.9

### 前端: RaceTacticsPage (651 行)
**借鉴**: TrainingPeaks Race Plan / WKO5 Race Day 风格

**布局** (3 列)
- **左 1/4** (288px): 会话列表 (卡片, 优先级 A/B/C 标签, 消息数 + 附件数)
- **中 1/4** (320px): 比赛信息 + 路书附件 + AI 最终战术
- **右 1/2**: 聊天 (用户/AI 气泡, RAG 来源标签, 输入框)

**功能**
- [x] **新建战术**: 对话框填 比赛名称/日期/距离/爬升/类型/优先级/天气/路线
- [x] **AI 自动建议**: 按钮 "AI 给我一个建议" — 基于比赛信息+路书+KB 生成完整战术
- [x] **聊天对话**: SSE 流式 (跟 ChatPage 一样), AbortController 停止
- [x] **RAG 来源标签**: 消息生成后显示训练百科引用
- [x] **路书上传**: 拖拽/点击上传 PDF/PNG/JPG/WEBP, 20MB 限制, PDF 自动 OCR
- [x] **删除**: 会话/附件都可删
- [x] **最终战术**: AI 生成后存为 final_strategy, 用户可查看

**Sidebar 加入口**: Trophy 图标, "比赛战术" 标签

### 沙箱验证
- TSC: **0 错**
- pytest: **41 passed**
- Vite build: 1.220MB JS / 77KB CSS (gzip 340KB / 17KB)
- 业务端点 + 10 race-tactics 端点全 200/正常

## 端点
- V0.7.5.9: 98 paths / 115 method
- V0.7.5.10: 98 paths / 115 method (无变化, 全前端)

## 完整工作流 (用户角度)
1. Sidebar 选 "比赛战术" → 列表页
2. 点 "新建战术" → 填比赛信息 → 创建
3. (可选) 上传路书 PDF → 知识库自动 OCR 提取文本
4. 点 "AI 给我一个建议" → 看 AI 完整战术
5. 跟 AI 讨论: "Day2 山地怎么分配体力?" / "补给间隔?" 等
6. 满意后, AI 自动存的 final_strategy 留在会话里, 比赛前复习
