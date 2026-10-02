# V0.8.3 进度快照 (2026-09-19 用户额度暂停)

> **状态**: 用户额度耗尽, 暂停所有 team plan + agent 工作
> **恢复方式**: 用户额度重置后说"继续", 我会按此快照恢复

---

## 1. 当前阶段

**目标**: 准备 V0.8.3 操作贯通计划的输入材料 (完整问题笔记本)
**原计划**: 4 个并行 track + 1 个 synthesis (deep-engineering-handbook 深度)
**状态**: 1/5 完成, 4/5 中断

---

## 2. 已完成交付物 (5 份, 可直接使用)

| # | 文件 | 内容 | 大小 |
|---|---|---|---|
| 1 | `_review/PROGRESS_SNAPSHOT_2026-09-19.md` | 本文件 (进度快照) | - |
| 2 | `_review/TP_OPERATIONAL_UX_AUDIT.md` | TP 操作对标报告 (操作维度) | 16.6 KB |
| 3 | `_review/TP_UX_AUDIT.md` | TP 功能对标报告 (上一轮偏题留作参考) | 18.6 KB |
| 4 | `_review/V0.8.3_PLAN.md` | V0.8.3 三批次执行计划 | 16.5 KB |
| 5 | `_review/track-frontend-flow/deliverable.md` | 前端流审计 22 条新 issue + 5 量化指标 | 团队产出 |

---

## 3. 中断的 team plan

### Plan 配置
- **plan_id**: `plan_1ca7f41a`
- **plan 文件**: `/workspace/.mavis/plans/v0823-ux-audit.yaml`
- **状态**: `cancelled`
- **原因**: 用户额度耗尽, 用户主动 cancel

### 任务完成度

| Task ID | 状态 | 进度 | 备注 |
|---|---|---|---|
| `track-frontend-flow` | ✅ done | 100% | deliverable.md 已写, 等 verifier 验收 (未触发) |
| `track-api-data-flow` | ⏸ interrupted | 0% | producer session 还活着但被 cancel, deliverable.md 未写 |
| `track-visual-density` | ⏸ interrupted | 0% | 同上 |
| `track-content-organization` | ⏸ interrupted | 0% | 同上 |
| `synthesis-notebook` | ⏸ blocked | 0% | 依赖前 4 个 track |

### Producer session id (恢复时如需 reconnect)

| Task | session_id |
|---|---|
| track-frontend-flow | 443354753208540 |
| track-api-data-flow | 443354693788080 |
| track-visual-density | 443354753208541 |
| track-content-organization | 443354753208542 |

注: session 在 cancel 后会超时被回收, 恢复时建议**直接新跑**, 不要 reconnect。

---

## 4. 恢复时要做的事

### 步骤 1: 检查已有材料够不够

如果用户说"够了, 开干":
- 跳过 team plan
- 直接进 V0.8.3 B1 实施 (按 `_review/V0.8.3_PLAN.md` B1 段)
- 用户原话: "**给出计划**" → 计划已写好, 直接执行

如果用户说"继续挖完":
- 跑剩下 3 个 track (api / visual / content)
- 然后跑 synthesis
- **建议节省额度方案**: 每个 track 各 1 轮 (~5-10 min), 总 30-40 分钟, 不重复 track-frontend-flow

### 步骤 2: 恢复命令

如果用户说"继续挖":
- 重读 `/workspace/.mavis/plans/v0823-ux-audit.yaml`
- 把已完成 task 标记掉 (track-frontend-flow 跳过)
- 重跑剩下 4 个
- 或者: 我直接**手动写 3 个 deliverable** (基于已有代码扫描 + 已有 track-frontend-flow 的素材), 不调 team

### 步骤 3: V0.8.3 实施前确认

无论走哪条路, V0.8.3 B1 开干前要跟用户确认:
1. V0.8.2 18 项 UX 改动 commit message 用什么?
2. V0.8.3 B1 范围确认 (6 项 P1: Library拖/Chat解析/Phases应用/Builder加日历/Activity模板/Library多选)
3. 是先打 V0.8.2 zip (含架构预留), 还是直接 V0.8.3 一起打?

---

## 5. 用户硬规则 (不能忘)

### 工作流 (memory: `user-code-update-workflow`)
- ✅ **任何 git commit / git push 必须用户明确同意**
- ✅ **先给 zip 预览, 用户同意后才推 GitHub**
- ✅ 用户原话: "干完给我测, 我同意了才能 push"

### 工程导向
- ✅ 用户原话: "我要的是先搞实在的, 工程的, 而不是只做宣传这些表面功夫"
- ✅ 不做 marketing / 表面功夫
- ✅ 重在工程价值

### 用户视角优先
- ✅ 用户原话: "不要局限于开发者视角. 你要进行详细测试... 重点优化使用体验"
- ✅ UX 改进要看 user perspective, 不是 dev perspective

### 不打包
- ✅ 用户决定: 现阶段不做 desktop 打包, 只预留接口 (已加 platform.ts 抽象)

### V0.8.2 测试状态 (V0.8.3 改完验证用)
- `pytest`: 82 passed / 7 failed / 2 skipped
- 7 failed: 6 个 IDOR fixture (`sqlite3.OperationalError`) + 1 个 Conformal
- 6 Pydantic V2 deprecation warnings
- 改完别破这两组数据

---

## 6. 用户原话 (供后续回复参考, 不要复述)

### 痛点类
- "我说的是操作体验: 我先举几个例子, 你接着挖相似的"
- "我说的是操作体验: 我先举几个例子, 你接着挖相似的。1: 知识库内容杂乱, 部分访问不了, 通过侧边栏直接访问某个知识库文件访问不了。2: 日历, 训练等内容各管各的, 我新建的训练没法拖到计划里, 计划加不进日历里, AI教练给出的回复不能直接加到课程里。3: 前端一眼AI味道, 令人审美疲劳, TP的风格就很好看。"
- "我说的是操作体验: 我先举几个例子, 你接着挖相似的"
- "我说的是功能差距就完蛋了, 我说的不是功能"

### 决策类
- "干完给我测, 我同意了才能 push"
- "我要的是先搞实在的, 工程的, 而不是只做宣传这些表面功夫"
- "不要局限于开发者视角"
- "拉团队挖, 这种大事要上团队！！！"
- "我的10000积分够用吗? 我额度用完了"
- "先停一下"
- "进度记录好, 等我额度重置后继续"

---

## 7. V0.8.3 范围 (按 V0.8.3_PLAN.md)

### B1 模块互通 (3-4 天) — 用户最高频痛点
- B1-1 Library workout 真·拖到 Calendar (HTML5 DnD 跨页)
- B1-2 Chat 回复含 workout JSON → "加入 Builder" 按钮
- B1-3 Phases → "应用到日历" 一键生成 (后端 +1 端点)
- B1-4 Builder → "保存并加入日历"
- B1-5 ActivityDetail → "作为模板"
- B1-6 Library 多选 workout 批量加入日历

### B2 KB / Chat / Insights 体验贯通 (2 天)
- B2-1 Sidebar KB 加最近访问 + 收藏 (localStorage)
- B2-2 KB 顶部搜索直达
- B2-3 Chat 历史记录 + 搜索
- B2-4 Insights 聚合入口 (Sidebar 单入口)

### B3 视觉降 AI 味 (3-4 天) — 品牌感
- B3-1 设计系统 theme 换皮 (TP 风)
- B3-2 圆角统一 6px (批量改 63 处)
- B3-3 Logo 渐变去色 (Sidebar + TopBar)
- B3-4 Empty state 素描化
- B3-5 卡片状态色条 (border-l-4)

### 不做
- ❌ Mobile UX 单独优化 (V0.9.x)
- ❌ Premium Paywall
- ❌ 教练侧 / 多人协作
- ❌ Recurring / Layout 自定义 (V0.8.4)
- ❌ StackUp
- ❌ 改后端业务逻辑 (只加 1 个 Phases apply 端点)

---

## 8. 待用户决策 (恢复时问)

1. **继续挖剩下的 3 个 track + synthesis?**
   - A: 是, 全挖完 (省额度方案)
   - B: 不挖了, 直接进 V0.8.3 B1 实施
   - C: 只补最关键的 (e.g. 视觉 track, 因为用户提到 AI 味)

2. **V0.8.2 18 项 UX 改动是否要 commit?**
   - A: 暂不 commit, 等 V0.8.3 一起
   - B: 现在 commit V0.8.2, V0.8.3 再 commit
   - C: 用户会自己 commit

3. **V0.8.3 优先级确认?**
   - A: 全做 B1 (3-4 天)
   - B: B1 + B2 (5-6 天)
   - C: B1 + B3 (7 天, 跳过 B2)
   - D: B1 + B2 + B3 (9 天)

---

## 9. 备份位置速查

```
/workspace/cycling-coach/_review/
├── PROGRESS_SNAPSHOT_2026-09-19.md   (本文件)
├── TP_OPERATIONAL_UX_AUDIT.md        # TP 操作对标 ✅
├── TP_UX_AUDIT.md                    # TP 功能对标 ✅ (留作参考)
├── V0.8.3_PLAN.md                    # V0.8.3 计划 ✅
├── track-frontend-flow/
│   └── deliverable.md                # 前端流 22 条 issue ✅
├── UX_AUDIT_V0.8.1.md                # V0.8.1 原始审计
├── ENGINEERING_AUDIT_V0.8.1.md       # V0.8.1 工程审计
└── INSTALL.md                        # 安装说明

/workspace/.mavis/plans/
└── v0823-ux-audit.yaml               # team plan 配置 (要重跑用)
```

---

**快照完成。等用户额度重置后说"继续"。**