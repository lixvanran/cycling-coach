# Cycling Coach V0.8.2 UX 改动 — 安装指南

> 测试用，**不推 GitHub**。你 review 完告诉我 OK 才 commit + push。

## 包内容

| 文件 | 用途 |
|---|---|
| `ux-changes.patch` | 22 个 modified 文件的 git diff (138KB) |
| `GlobalSearch.tsx` | 新组件 — Cmd+K 全局搜索 (10KB) |
| `NotificationsBell.tsx` | 新组件 — 通知铃铛 (5KB) |
| `UX_AUDIT_V0.8.1.md` | 用户体验审计报告 (20KB, 改动前的依据) |
| `ENGINEERING_AUDIT_V0.8.1.md` | 工程审计报告 (18KB, 暂不修) |

## 应用步骤

```bash
# 1. 进你的本地项目目录
cd /path/to/your/cycling-coach

# 2. 备份（万一要回滚）
git checkout -b ux-v0.8.2-rc

# 3. 应用 patch (会改 22 个文件)
git apply ux-changes.patch

# 4. 放 2 个新文件
cp GlobalSearch.tsx apps/web/src/components/
cp NotificationsBell.tsx apps/web/src/components/

# 5. 前端补装一个依赖 (react-router-dom, build 需要的)
cd apps/web
npm install

# 6. 后端装环境
cd ../
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 7. 跑起来
./tools/start.sh  # 或 tools/start.bat (Windows)

# 8. 测完
git add -A
git diff --cached --stat  # 看改了哪些
```

## 改了什么 (18 项 UX)

| # | 问题 | 修复 | 文件 |
|---|---|---|---|
| U-1 | TopBar 搜索框死按钮 | Cmd+K 触发 GlobalSearch | `TopBar.tsx`, `GlobalSearch.tsx` (新) |
| U-2 | 12 处原生 alert/confirm | 全部换 `useConfirm` hook + `toast.warn/error` | `ConfirmDialog.tsx` (加 hook), 8 个 page |
| U-3 | Profile 改完不点保存全丢 | 1.5s 自动保存 + dirty 警告 + beforeunload | `Profile.tsx` |
| U-4 | AI 报告 60s 超时错乱 | 120s + elapsed 显示 + 超时明确提示 | `ActivityDetail.tsx` |
| U-5 | "Mock 模式" 顶栏显眼 | 移到底部状态条 | `TopBar.tsx`, `Sidebar.tsx` |
| U-6 | Sidebar 标签混淆 | "训练洞察" → "HRV / 训练健康" 等 | `Sidebar.tsx` |
| U-7 | Sidebar 15 项平铺 | 5 大分组 (训练/AI/计划/数据/设置) | `Sidebar.tsx` |
| U-8 | 通知铃是死按钮 | NotificationsBell 组件 + 未读 badge | `TopBar.tsx`, `NotificationsBell.tsx` (新) |
| U-9 | AI 报告没法取消 | 加"取消"按钮 (前端 abort + toast 提示) | `ActivityDetail.tsx` |
| U-10 | InsightsPage 加载/空状态简陋 | EmptyState + LoadingSkeleton | `InsightsPage.tsx` |
| U-12 | AI 流式 `[THINK]` hack | 改 ## Thinking/## Answer markdown 切 | `ChatPage.tsx`, `chat.py` prompt |
| U-13 | ComparePage 错误简陋 | toast + EmptyState + 重试按钮 | `ComparePage.tsx` |
| U-14 | 2 处直接 fetch | 走 api 客户端 | `Profile.tsx`, `LibraryPage.tsx` |
| U-15 | 重复文件没检测 | 上传后查同日期同时长, 命中弹 toast | `ImportPage.tsx` |
| U-20 | KB 搜索只高亮第一个 | 高亮所有匹配 + 标题命中 badge | `KnowledgeBasePage.tsx` |
| U-22 | AI KB 引用点不进去 | 引用加"打开 →" 按钮 | `ChatPage.tsx` |
| U-23 | 比赛战术卡片无类型色 | race_type 色条 + 优先级徽章更醒目 | `RaceTacticsPage.tsx` |
| U-25 | Toast 不能 undo | Toast 加 action 字段 | `Toast.tsx` |

## 已知的 V0.8.1 旧问题 (没修, 留作 V0.8.3+)

- ❌ README 数字虚标 (137+2 skip 实际 82+7+2)
- ❌ 7 个测试 fixture 挂 (IDOR / Conformal)
- ❌ 4 处 Pydantic V2 `class Config` deprecation 警告
- ❌ `.github/workflows/` 还没建 (CI 0 落地)
- ❌ `requirements.txt` 严重过期

## review 关注点

1. **GlobalSearch** - Cmd+K 弹 dialog, 搜活动 (按日期/编号) + KB (按 FTS5)
2. **useConfirm hook** - `const ok = await confirm({title, message, variant: "danger"})`
3. **ChatPage 流式解析** - 改成 markdown 标题切, prompt 加了 "## Thinking / ## Answer" 输出要求
4. **Profile 自动保存** - 1.5s debounce + 字段 amber 高亮 + beforeunload 警告
5. **Toast undo** - 调用方式 `toast.success("已删除", {action: {label: "撤销", onClick: restore}})`

## 验证

- `vite build` 通过 (39.7s, 14 chunks, 0 error)
- `pytest` 82 passed / 7 failed (改前同样) / 2 skipped
- 服务起得来, `/api/health` `/api/diagnose` `/api/version` `/api/athlete` 200 OK
- KB 搜索 "FTP" 出 30+ 结果带高亮

## 决定

- **A** — 全 OK, commit + push
- **B** — 某项要改, 说哪条
- **C** — 全部 OK 但还要再加几个 UX 改动
- **D** — 看到不对, 整个回滚 `git checkout .`
