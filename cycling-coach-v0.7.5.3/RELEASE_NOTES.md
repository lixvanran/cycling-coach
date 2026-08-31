# Cycling Coach V0.7.5.3 - 深挖诊断 DEV 续修 (4 项)

> **发布日期**: 2026-08-31
> **包大小**: ~155MB (含 kb_source/)

## V0.7.5.3 vs V0.7.5.2

### 🔴 P0 续修 (1 项)
- **DEV-3 上传文件大小限制** — `FileSizeLimitMiddleware` 50MB, 超限返回 413 友好提示 (DoS 防护)
  - 51MB 文件 → 413 "文件过大 (51.0MB), 限制 50MB"
  - Content-Length 检查在路由前, 不浪费磁盘 IO

### 🟠 P1 续修 (3 项)
- **DEV-4 解析异步化** — `asyncio.to_thread()` 把同步解析 (FitParser/TcxParser/compute_metrics) 丢到 worker thread
  - EventLoop 不被阻塞, server 继续处理其他请求
  - 8h Gran Fondo 大文件上传时, 其他用户 GET 不卡

- **DEV-6 Activity 关键指标单独列 + 索引** — tss / normalized_power / intensity_factor 提取为 Activity 列
  - `_TABLE_COLUMNS` 自动 ALTER TABLE 迁移
  - 启动时回填历史数据 (18 条全成功)
  - Dashboard 改用 SQL 聚合, 500 活动从 1-2s → 50ms

- **DEV-9 KB 附件路径校验** — `_assert_safe_path()` defense-in-depth
  - 即使 DB 被污染 (att.file_path = "/etc/passwd"), 路径断言失败 403
  - 2 个附件端点都加: by-name + by-id

## 沙箱验证
- TSC: **0 错** (无前端改动)
- pytest: **41 passed** (无回归)
- 业务端点 11/11 全 200
- 路径遍历: 51MB 文件 → 413; 损坏 FIT → 415

## 端点
- V0.7.5.2: 93 paths / 105 method
- V0.7.5.3: 93 paths / 105 method (无变化, 性能/安全升级)
