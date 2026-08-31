# Cycling Coach V0.7.5.4 - 深挖诊断 DEV 续修 (5 项)

> **发布日期**: 2026-08-31

## V0.7.5.4 vs V0.7.5.3

### DEV-13 巨型 router 拆分
- [x] 新建 `_activities_shared.py` (106 行) — 抽 Pydantic + helpers
- [x] activities.py: 共享代码搬到 shared, 路由端点保留
- 12 routes 完整, 0 改动 (FastAPI prefix 不变)

### DEV-16 KB 增量更新
- [x] `_setup_fts(engine, full_rebuild=False)` 增量模式
- [x] 默认 `INSERT OR REPLACE` 同步 chunks, `DELETE` orphan
- [x] `full_rebuild=True` 仍支持手动全量重建
- 调一次 5-20s → 0.5s 增量更新

### DEV-17 XSS sanitization
- [x] ChatMessage.tsx 加 `rehypeSanitize` 到 `rehypePlugins`
- [x] 装 `rehype-sanitize` 依赖
- [x] ActivityDetail 报告用纯 text 渲染, 默认 safe

### DEV-19 SQL 注入白名单
- [x] `_ALLOWED_TABLES` 白名单 (15 个表)
- [x] `database.py:93/131` PRAGMA table_info 前 assert
- 即使 `_TABLE_COLUMNS` 被污染, 也无法注入任意 SQL

### DEV-20 KB 整批事务
- [x] 252 附件导入从 252 次 commit → 1 次 commit
- [x] 失败时 SQLAlchemy Session context 自动 rollback
- 导入失败不留半个 KB

## 沙箱验证
- TSC: **0 错**
- pytest: **41 passed**
- 业务端点 11/11 全 200

## 端点
- 93 paths / 105 method (无变化)
