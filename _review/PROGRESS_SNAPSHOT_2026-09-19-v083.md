# V0.8.3 B1 进度快照 (2026-09-19 用户额度暂停 v2)

> **状态**: 用户额度耗尽, 暂停
> **恢复方式**: 用户额度重置后说"继续", 我按此快照恢复
> **前一快照**: `_review/PROGRESS_SNAPSHOT_2026-09-19.md` (V0.8.2 阶段, 已完成)

---

## 1. 当前阶段

**目标**: V0.8.3 批次 1 — 模块互通 6 项实施 + 集成验证 + 打 zip
**当前状态**: 6 项功能已完成, 5 项已通过 Verifier 独立验收, B1-5 还在 verifying, synthesis (集成 + zip) 阻塞等待
**关键产出**: zip **还没生成**

---

## 2. Plan 配置

- **plan_id**: `plan_bfeceb8e`
- **plan 文件**: `/workspace/.mavis/plans/v0823-b1-impl.yaml`
- **状态**: `running` (不是 cancelled, 是用户额度暂停)
- **timeout 设置**: 每 task 30 min, B1-3 已 extend 10 min

---

## 3. 任务完成度 (2026-09-19 18:11 实测)

| Task ID | Title | Producer | Verifier | 备注 |
|---|---|---|---|---|
| `b1-1-lib-drag` | Library workout 拖到 Calendar | ✅ done | ✅ PASS | HTML5 DnD + Safari fallback |
| `b1-2-chat-builder` | Chat → Builder 解析 workout JSON | ✅ done | ✅ PASS | chat.py 加 workout JSON 规则 + lib/builderBlocks.ts 新文件 |
| `b1-3-phases-apply` | Phases 一键应用到日历 | ✅ done | ✅ PASS | **新增 PhaseWorkout 表 + 7 测试 + 新端点** |
| `b1-4-builder-calendar` | Builder 保存并加入日历 | ✅ done | ✅ PASS | ScheduleModal 提到 common/ 共用 |
| `b1-5-activity-template` | ActivityDetail 作为模板 | ✅ done | ⏳ verifying | useEffect 监听 query, 自动生成 3 块模板 |
| `b1-6-multi-add` | Library 多选批量加入日历 | ✅ done | ✅ PASS | 多选 checkbox + 3 种间隔模式 |
| `b1-synthesis-verify` | 集成验证 + 打 zip 1 | ⏸ blocked | - | 依赖前 6 项 |

---

## 4. 关键变更 (与 V0.8.2 base 相比)

### 前端 (5 个文件)
- `apps/web/src/pages/LibraryPage.tsx` — 多选 + 拖拽 + 改 ScheduleModal import (B1-1 + B1-6 + B1-4)
- `apps/web/src/pages/CalendarPage.tsx` — 接收 library drop, 蓝色虚线高亮 (B1-1)
- `apps/web/src/pages/BuilderPage.tsx` — from_chat + from_activity useEffect, "保存并加入日历"按钮 (B1-2 + B1-4 + B1-5)
- `apps/web/src/pages/ChatPage.tsx` — workout JSON 检测 + addToBuilder (B1-2)
- `apps/web/src/pages/ChatMessage.tsx` — extractWorkoutFromContent + "➕ 加入 Builder"按钮 (B1-2)
- `apps/web/src/pages/ActivityDetail.tsx` — "📋 作为模板"按钮 (B1-5)
- `apps/web/src/pages/PhasesPage.tsx` — "📅 应用到日历"按钮 + 模态框 (B1-3)
- `apps/web/src/App.tsx` — /plan/builder route (B1-5)
- `apps/web/src/components/common/ScheduleModal.tsx` (新) — 共用模态框 (B1-4)
- `apps/web/src/lib/api.ts` — 加 applyPhaseToCalendar 方法 (B1-3)
- `apps/web/src/lib/builderBlocks.ts` (新) — 共享 Block 类型 (B1-2)

### 后端 (3 个文件)
- `cycling_coach/ai/prompts/chat.py` — 加 ```workout JSON 输出规则 (B1-2)
- `cycling_coach/api/routers/phases.py` — 加 `POST /phases/{id}/apply` 端点 (B1-3)
- `cycling_coach/data/models.py` (推测, 待 verify) — 加 `PhaseWorkout` model + 关联表

### 测试 (1 个新文件)
- `tests/test_phases_apply_b13.py` (新) — 7 个 pytest 覆盖新端点

### 测试状态变化
- baseline V0.8.2: 82 pass / 7 fail / 2 skip
- V0.8.3 B1 后: **89 pass / 7 fail / 2 skip** (+7 新 pass, 7 fail/2 skip 不变)

---

## 5. 已知问题 / 风险

### 1. HTML5 DnD 单 tab 限制 (B1-1 verifier 发现)
- 单浏览器 tab 内, mouse 按住拖到 Sidebar link 上**不会触发** link click
- 用户必须: 单 tab 走 Safari fallback "+ 加到日历"按钮 / 跨 tab 拖
- **可选修复**: 用 react-dnd (~30KB) 替代 native DnD, 但会改依赖
- **当前决策**: 接受现状, 不动

### 2. PhaseWorkout 新表 (B1-3)
- 新增了 schema 改动 (`PhaseWorkout` 关联表)
- 这是 V0.8.3_PLAN.md 写的"只加 1 个端点"之外的改动
- Worker 说"extending schema, not restructuring" — 在合理范围, 但**需要用户 review**
- 决策: 不动, 接受产出

### 3. 没 git commit / 没 push (用户硬规则遵守)
- 所有改动在工作区, 没推 GitHub
- 集成任务里明确写 "不 git commit / 不 push"

---

## 6. 恢复时要做的事

### 步骤 1: 检查 plan 状态
```bash
team status --plan-id plan_bfeceb8e
```
- 看 B1-5 verifier 结果是否 PASS
- 如果都 PASS, 进入决策

### 步骤 2: Owner 决策 (manual_retry / accept)

如果 B1-5 也 PASS, 我提交决策 accept 全部, 让 synthesis-verify 启动。

```json
{
  "last_cycle": [
    {"task_id": "b1-1-lib-drag", "verdict": "accept"},
    {"task_id": "b1-2-chat-builder", "verdict": "accept"},
    {"task_id": "b1-3-phases-apply", "verdict": "accept"},
    {"task_id": "b1-4-builder-calendar", "verdict": "accept"},
    {"task_id": "b1-5-activity-template", "verdict": "accept"},
    {"task_id": "b1-6-multi-add", "verdict": "accept"}
  ],
  "plan_complete": false
}
```

### 步骤 3: synthesis-verify 自动启动
- Coder 跑全栈验证 (vite build + pytest + 关键 API curl)
- 打 V0.8.3-B1 zip
- 写 V0.8.3_B1_DELIVERY.md
- Verifier 独立检查 zip

### 步骤 4: 给用户 review zip
- zip 路径: `/workspace/cycling-coach-v0.8.3-b1-YYYYMMDD.zip`
- 不 commit / 不 push (按硬规则)

---

## 7. 用户硬规则 (不能忘)

### 工作流 (memory: `user-code-update-workflow`)
- ✅ **任何 git commit / git push 必须用户明确同意**
- ✅ **先给 zip 预览, 用户同意后才推 GitHub**
- ✅ 用户原话: "干完给我测, 我同意了才能 push"

### 工程导向
- ✅ 用户原话: "我要的是先搞实在的, 工程的"
- ✅ 不做 marketing / 表面功夫

### 用户视角优先
- ✅ 用户原话: "不要局限于开发者视角. 你要进行详细测试... 重点优化使用体验"

### 不打包 (V0.8.x 阶段)
- ✅ 用户决定: 不做 desktop 打包, 只预留接口 (已加 platform.ts 抽象)

---

## 8. 已交付材料 (本次会话)

| 文件 | 状态 | 大小 |
|---|---|---|
| `cycling-coach-v0.8.3-pre-20260919.zip` | ✅ 已打 (V0.8.2 状态) | 6.2 MB / 1116 文件 |
| V0.8.3-B1 改动在工作区, 未 commit | ✅ 已写代码 | (待 build) |
| V0.8.3-B1 zip | ❌ 待 synthesis-verify 完成 | - |
| V0.8.3_B1_DELIVERY.md | ❌ 待 synthesis-verify 完成 | - |

---

## 9. 备份位置速查

```
/workspace/cycling-coach/_review/
├── PROGRESS_SNAPSHOT_2026-09-19.md       # 上次快照 (V0.8.2 阶段)
├── PROGRESS_SNAPSHOT_2026-09-19-v083.md  # 本次快照 (V0.8.3 B1 阶段)
├── UX_ISSUES_NOTEBOOK.md                 # 90 条 issue 笔记本
├── V0.8.3_PLAN.md                        # 三批次计划
├── TP_OPERATIONAL_UX_AUDIT.md            # TP 操作对标
├── TP_UX_AUDIT.md                        # TP 功能对标 (留作参考)
└── team-output/                           # 4 路审计原始 deliverable

/workspace/.mavis/plans/
└── v0823-b1-impl.yaml                    # V0.8.3 B1 team plan

/workspace/.mavis/plans/plan_bfeceb8e/
├── outputs/                               # 6 个 task deliverable
└── board.md                               # 进度记录
```

---

## 10. 额度重置后用户需决策

1. **要不要换 react-dnd?** (解决单 tab 拖拽问题)
2. **PhaseWorkout 新表 OK 吗?** (B1-3 加的 schema 改动)
3. **下一步进 B2 还是 B3?**
   - B2: KB / Insights 体验贯通
   - B3: 视觉降 AI 味

---

**快照完成。等用户额度重置后说"继续"。**