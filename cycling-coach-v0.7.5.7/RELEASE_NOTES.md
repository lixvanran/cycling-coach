# Cycling Coach V0.7.5.7 - UX-13/15 (KB 懒加载 + RPE onboarding)

> **发布日期**: 2026-08-31

## V0.7.5.7 vs V0.7.5.6

### UX-13 KnowledgeBasePage 懒加载
- [x] KB 文档内图片加 `loading="lazy" + decoding="async"`
- 浏览长文档时, 视口外图片不下载, 滚动到才加载
- 滚动卡顿减少

### UX-15 RPE onboarding
- [x] 上传活动成功后, 1.5s 后弹 `toast.info`
- [x] 提示 "训练后 30 分钟内填 RPE 主观疲劳最准, 打开活动详情记录"
- 用户上传后立即知道 RPE 重要性, 不再 1 周后发现

## 沙箱验证
- TSC: **0 错**
- pytest: **41 passed**
- Vite build: 1.219MB JS

## 端点
- 93 paths / 105 method (无变化)

## 状态
报告 50 项问题剩:
- DEV-15 同步测试 (V0.7.6 单独)
- 附录 15 项 (V0.7.5.8)
