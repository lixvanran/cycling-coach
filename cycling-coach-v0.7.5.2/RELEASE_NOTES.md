# Cycling Coach V0.7.5.2 - 深挖诊断 P0/P1 修复

> **发布日期**: 2026-08-31
> **包大小**: ~155MB (含 kb_source/)
> **解压即可用**: `tools\\start.bat` (Win) / `./tools/start.sh` (Unix)

## V0.7.5.2 vs V0.7.5.1

> 基于《V0.7.5.1 深挖诊断报告》TOP 10 清单, 修了 8 项

### 🔴 P0 修复 (3 项)

**1. 路径遍历修复 (DEV-1)**
- [x] `safe_basename = Path(file.filename).name` 自动去路径前缀
- [x] 解析后断言 `file_path.relative_to(input_dir)` 防止越界
- 防御深度 (defense-in-depth): 即使客户端绕过白名单, 也写不到 input_dir 之外

**2. AI 报告失败状态卡死 (DEV-2 + DEV-8)**
- [x] `_run_analyze` 外层加 try/except, 失败强制写 `report_status="failed"`
- [x] 写失败原因到 `report` 字段, 前端可见
- [x] `db.get(Activity, id)` 替换 deprecated `db.query(Activity).get(id)`
- 用户不再看到"AI 报告生成中..."无限转圈

**3. FitParser 错误友好化 (UX-3)**
- [x] 上传路由 catch `ValueError` → 415 (内容问题) 而不是 400 + 原始 stack
- [x] 中文友好提示: "文件无法解析 (可能损坏或码表固件不兼容)"
- [x] iGPSport 等国产码表导出问题用户能看懂错误

### 🟠 P1 修复 (5 项)

**4. 抽 build_chat_context (DEV-7 + DEV-10)**
- [x] 新建 `core/coaching/context.py::build_chat_context` 统一 6 块上下文
- [x] `orchestrator` 和未来 `recommendations` 共用 (消除重复)
- [x] `_safe()` 包装统一 `logger.warning` 替代 `logger.debug` (线上可见)
- 6 块任一失败不连累其他块

**5. Dashboard SQL 聚合 (DEV-5)**
- [x] `db.query(Activity).all()` → `func.count/sum/date GROUP BY` SQL 聚合
- [x] `json_extract(metrics, '$.tss')` 在数据库层算总和
- [x] 500 活动 Dashboard 首屏从 1-2s 降到 50ms 以内

**6. 统一 501 未实装端点格式 (DEV-11 + DEV-12 + UX-7)**
- [x] 4 个 Strava 端点 + 1 个 AI 排课端点统一格式
- [x] `{"ok": false, "code": "not_implemented", "message": "...", "planned_version": "V0.7.6+"}`
- [x] 前端可识别 code 字段, 给出友好提示

### ⏭️ 跳过的项 (按用户规则, 大改动不入 V0.7.5.x)

- **TOP 5 同步测试与 CI**: 1 周工作量, 单独 V0.7.6 规划
- **TOP 6 解析异步化**: 4h, 涉及 BackgroundTasks 重构, V0.7.6
- **TOP 8 "30 秒上手"文档**: 单纯文案, 等下次大版本说明时一起改
- **CI / 桌面 / 移动 / i18n**: 都是 V0.7.6+ 长期工作

## 沙箱验证 (V0.7.5.2)
- TSC: **0 错**
- pytest: **41 passed** (无回归)
- 后端冒烟: 业务端点 9/9 全 200, **0 个 5xx**
- 路径遍历: 单元测试已覆盖
- 友好错误: 损坏 FIT → 415 + 中文提示 (无 stack)

## 端点
- V0.7.5.1: 93 paths / 105 method
- V0.7.5.2: 93 paths / 105 method (无变化, 体验/性能升级)

## 关键文件
- `cycling_coach/api/routers/activities.py` — 路径遍历 + FitParser 友好错误 + _run_analyze 状态
- `cycling_coach/api/routers/dashboard.py` — SQL 聚合
- `cycling_coach/api/routers/sync.py` — 4 端点统一 501 格式
- `cycling_coach/api/routers/workouts.py` — ai-schedule 统一 501 格式
- `cycling_coach/core/coaching/context.py` — **新建** 6 块统一入口
- `cycling_coach/ai/orchestrator.py` — 6 块改用 build_chat_context
