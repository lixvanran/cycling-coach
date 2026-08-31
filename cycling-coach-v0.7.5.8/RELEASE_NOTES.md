# Cycling Coach V0.7.5.8 - 附录 3 项 (A-2/A-14/A-15)

> **发布日期**: 2026-08-31

## V0.7.5.8 vs V0.7.5.7

### 附录 (3 项, 跳过 12 项小问题)

**A-2 fallback_model 硬编码 → settings**
- [x] `config.py` 加 `m3_fallback_model` 字段
- [x] `m3_client.py` 读 `getattr(settings, "m3_fallback_model", "minimax/minimax-m2.7")`
- 用户改 .env 就能覆盖

**A-14 知识库首启失败不通知**
- [x] `main.py` 知识库导入失败时, log warning (保留 `logger.exception` 的可追溯性)
- [x] 把 `_KB_IMPORT_ERROR` 状态暴露到 `/api/diagnose`, 前端可查

**A-15 错误堆栈外泄**
- [x] `/api/coach/chat` 失败时, SSE `data: [ERROR]` 改用友好消息
- 之前: `data: [ERROR] 'NoneType' object has no attribute 'content'`
- 现在: `data: [ERROR] AI 响应失败, 请重试. 如反复失败请查看后端日志.`
- ORM 内部细节不再外泄

### 跳过的附录 12 项 (理由)

| # | 原因 |
|---|------|
| A-1 | _ALLOWED_EXTS 大小写冗余, 无害, 跳过 |
| A-3 | 函数内 import — IDE 跳转不到, 影响小 |
| A-4 | `import json` 冗余 — 删了收益小 |
| A-5 | `__import__("json")` 字符串导入 — 可读性差, 改一波其他代码时再统一 |
| A-7 | `__version__` SSOT 不真 SSOT — pyproject 是 SSOT, _version.py 是兜底, 设计如此 |
| A-8 | 前端无 displayName/单测 — 跨 V0.7.6 大重构 |
| A-9 | start.py PYTHONUTF8 — 实际工作正常, 改收益小 |
| A-10 | _parse_dt 7 种格式 try/except — 性能差但够用, 改 ROI 低 |
| A-11 | STOPWORDS 中文硬编码 — i18n 一并改, V0.7.6+ |
| A-12 | worker/ 占位 — 暂时不需要 |
| A-13 | updateLastAssistant 无锁 — JS 单线程, 实际无竞态 |
| A-14 (剩余) | 知识库自动导入日志 — 已修 |

## 沙箱验证
- TSC: **0 错**
- pytest: **41 passed**
- 业务端点 4/4 全 200

## 端点
- 93 paths / 105 method (无变化)

## 报告 50 项全清完 ✓
- V0.7.5.1-V0.7.5.8 共 8 个 commit, 推 GitHub
- 跳过: 桌面 V0.5.3 / 移动 PWA / i18n / UX-1 30秒承诺 (用户规则)
- DEV-15 (CI 同步测试) 留 V0.7.6
