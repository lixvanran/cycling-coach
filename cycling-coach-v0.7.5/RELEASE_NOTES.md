# Cycling Coach V0.7.5 - 用户反馈修复 + 训练日记

> **发布日期**: 2026-08-29
> **包大小**: ~163MB (含 kb_source/)
> **解压即可用**: `tools\\start.bat` (Win) / `./tools/start.sh` (Unix)

## V0.7.5 vs V0.7.4.1

### Bug 修复 (用户反馈 3 项)
- [x] **Builder 拖动: 第一个积木块拖不上去** — EmptyDropZone 缺 onDragOver/onDrop, 已补
- [x] **Builder 保存: "做好课程无法保存"** — blocksToStructure 返回 dict `{version, blocks}`, 后端期望 `list[StepIn]`, 修成 flat list. structureToBlocks 兼容 list/dict 双向
- [x] **iGPSport FIT 解析鲁棒性** — 用户撤回 (自己保存成 .txt), 保留 V0.7.5 加的 try-except 友好错误兜底 (提升健壮性, 损坏文件给明确提示)

### 新功能: 训练日记 (Training Diary)
- [x] **数据模型** `training_diary` 表 — 借鉴 KB 训练百科 (caafd85d) + TrainingPeaks Daily Notes + WKO5 Daily Diary
- [x] **9 字段**: 训练感受 (1-5) / 心情 (1-5) / 睡眠时长 / 睡眠质量 (1-5) / 主观笔记 (Markdown) / 天气 / 装备补记 / 疼痛记录 / 关联活动
- [x] **5 端点** (`/api/diary` + `/template` + `/{date}` + POST upsert + DELETE):
  - `GET /api/diary?days=30` 最近 30 天
  - `GET /api/diary/template` KB 训练日记模板 (字段 + prompts + daily factors)
  - `GET /api/diary/{date}` 某天
  - `POST /api/diary` upsert (支持 partial update, 用 Pydantic `exclude_unset=True`)
  - `DELETE /api/diary/{date}` 删除 (404 if 不存在)
- [x] **前端 DiaryPage** (485 行) — 时间导航 + 评分组件 (1-5 圆角按钮) + Markdown 文本域 + KB 模板提示侧栏 (可点击插入) + 最近 30 天快速跳转 + 自动保存 (1.5s debounce)
- [x] **Sidebar 加入口**: NotebookPen 图标, "训练日记"

### 版本统一
- [x] `_version.py` + `pyproject.toml` + `package.json` (root + apps/web) → V0.7.5

## 沙箱验证 (V0.7.5 端到端)
- TSC: **0 错** (BuilderPage + DiaryPage + 共享类型)
- pytest: **41 passed** (无回归)
- Vite build: **1.127MB JS / 76KB CSS** (gzip 318KB JS / 17KB CSS)
- 后端冒烟: 105 method, **0 个 5xx**, 49 个 2xx, 50 个 4xx (参数缺失正常), 4 个 501 (Strava 预留), 2 个 0 (超时)
- diary 端点: list/template/get/upsert/delete 全 200
- builder: blocksToStructure 改 list, upsert 成功

## 端点
- V0.7.5: 88 paths / 100 method
- V0.7.5: **93 paths / 105 method** (+5 diary)

## 端点清单 (新增 5)
- `GET    /api/diary?days=30`     最近 N 天
- `GET    /api/diary/template`     KB 训练日记模板
- `GET    /api/diary/{date}`       某天
- `POST   /api/diary`              upsert
- `DELETE /api/diary/{date}`       删除

## 没 commit / 没 push
按用户规则, 修改留在 working tree, 等显式 push 同意.
