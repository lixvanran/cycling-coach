# Cycling Coach V0.7.5.6 - UX 体验批量修复 (4 项)

> **发布日期**: 2026-08-31

## V0.7.5.6 vs V0.7.5.5

### UX-8 AI chat 超时机制
- [x] ChatPage 加 30s 慢响应警告 (toast.warn "AI 响应较慢, 可点停止")
- [x] 120s 硬超时 (AbortController + toast.error "AI 响应超时, 已自动取消")
- 用户不再因 M3 API 卡住而永远等待

### UX-9 AI 报告生成计时器
- [x] ActivityDetail 加 `ElapsedCounter` 组件 (`useState + setInterval`)
- [x] 显示 `(0:23)` 这样的已等待时长
- 用户知道在等多久, 不会以为卡死

### UX-11 ActivityDetail loading skeleton
- [x] 灰块骨架 (animate-pulse) 替代 "加载中…"
- [x] 标题 + 4 个 MetricCard + 1 大图 + 2 小图 布局
- 加载时不再白屏, 用户知道页面在加载

### UX-12 Calendar link/unlink/markDone 友好提示
- [x] link 活动 → "已标记完成 ✓" 成功 toast
- [x] unlink 计划课 → "已解除关联" toast
- [x] 错误 → toast.error 友好提示
- 用户每个操作都有反馈

## 沙箱验证
- TSC: **0 错**
- pytest: **41 passed**
- Vite build: 1.219MB JS / 77KB CSS

## 端点
- 93 paths / 105 method (无变化)
