# Changelog / 变更日志

All notable changes to this project will be documented in this file.

本项目的所有重要变更都将记录在此文件中。

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased] / 下一版

### Planned / 计划
- LLM 思维扩散器 (Tree-of-Thoughts / 自研多 agent 推理)
- 训练回归模型 (ftp-predictor 集成)
- AsyncM3Client + httpx (5 路 LLM 真并发)
- Vite manualChunks + 路由 lazy (前端 886KB → 300KB)
- KB embedding 上线 (all-MiniLM-L6-v2 80MB)
- HRV 趋势分析
- 自动周报 PDF 生成
- 自动洞察告警
- AI 训练建议生成

## [V0.7.8] - 2026-08-31 — Foundation 1.0 (上"大家伙"前的地基)

### Added / 新增
- **chat 持久化**: 2 张新表 `chat_sessions` / `chat_messages` (含思维树字段 parent_id / node_path / thought_kind / score)
- **6 个 chat 端点**: POST/GET/DELETE sessions, get/add messages, update tree
- **ML 推理基础设施**: `core/ml/` 4 文件 (registry / feature_pipe / _mock / __init__)
- **5 个 ML 端点**: `POST /api/ml/predict/ftp` + models list/register/activate + predictions
- **2 张 ML 表**: `ml_predictions` (推理归档) + `ml_model_meta` (版本管理)
- **5 个新配置字段**: ml_models_dir / ml_active_ftp_model / ml_device / ml_max_batch / ml_use_onnx / ml_conformal_coverage
- **2 个新依赖**: `joblib>=1.3,<2.0` + `onnxruntime>=1.16,<2.0` (torch 留 V0.7.7+)
- **mock_engine 抽离**: `ai/mock_engine.py` 214 行, 从 m3_client.py 抽离 160 行 mock 业务逻辑
- **15 个 chat 测试 + 7 个 ML 测试** (总 41 → 63)

### Changed / 变更
- **SQLite WAL**: `journal_mode=WAL` + `synchronous=NORMAL` + `busy_timeout=5000ms`
- **索引补齐**: `ix_activities_tss` / `ix_activities_normalized_power` / `ix_act_athlete_start` / `ix_daily_metrics_athlete_date` (V0.7.5.3 声明了但 _auto_migrate 没建)
- **samples_json defer**: `activities.py:271` 改 `.options(defer("samples_json"))` + 改 SQL 端 tss/np 过滤
- **trends.py 5 个端点 SQL 聚合**: 不再 Python 端过滤, 走索引
- **优雅关闭**: `uvicorn.run(timeout_graceful_shutdown=10)` + SIGTERM handler
- **tools/stop.py**: SIGTERM → 8s 后 SIGKILL fallback (Windows 用 taskkill 不带 /F)
- **修了 _ALLOWED_TABLES 死代码** (V0.7.5.4 DEV-19 引用了但没定义)
- **m3_client.py**: 436 → 262 行 (-40%)
- **README.md / INSTALL**: V0.6.1 → V0.7.8

### Performance / 性能
- 单活动 1MB 字段不再吃全表内存 (defer)
- ORDER BY tss 走 `ix_activities_tss` 索引 (实测 EXPLAIN)
- 多 BackgroundTask 写库不撞锁 (WAL)
- 优雅关闭 4s 内完成 (旧: kill -9 直接砍)

### License / 协议
- 主项目: MIT
- 知识库: 严格保护 (kb_source/LICENSE, 中英双语)
- **不变**

## [V0.7.5.9+10] - 2026-08-30 — 比赛战术规划 (Race Tactics)

### Added / 新增
- **3 张表**: `race_tactics_sessions` / `messages` / `attachments` (路书 + 7 种 race_type + A/B/C 优先级)
- **10 端点**: CRUD + upload (PDF 解析 pypdf) + download + messages (SSE) + suggest
- **AI prompt**: 比赛信息 + athlete_ctx + 路书 OCR + KB 检索 (4-5 chunks, "竞技百科"/"比赛路线看什么"/"比赛前都要做什么"/"比赛如何补充能量")
- **RaceTacticsPage 651 行**: 三列布局 (列表/信息+路书/聊天), CreateSessionDialog, SSE 流式 fetch, RAG 来源标签
- **Sidebar Trophy 图标入口**

## [V0.7.5.1 - V0.7.5.8] - 2026-08-22 ~ 2026-08-30 — KB 精准 + P0/P1 修复 + 性能 + UX 批量

(V0.7.5.1-5.8 共 8 个子版本, 报告 40 项收口 39 项, 11 项跳过有理由)

### 主要改动
- **V0.7.5.1**: KB 侧栏二级菜单 + AI 抽句精准 + 修复空页路由
- **V0.7.5.2**: 深挖诊断 P0/P1 8 项 (路径遍历 / AI 报告失败状态 / 友好错误 / 抽 build_chat_context / SQL 聚合 / 501 格式统一)
- **V0.7.5.3**: DEV-3/4/6/9 (50MB 上传 + asyncio.to_thread + 关键指标索引 + KB 路径校验)
- **V0.7.5.4**: DEV-13/16/17/19/20 (router 拆分 + KB 增量 + XSS sanitize + SQL 白名单 + 整批事务)
- **V0.7.5.5**: DEV-18 依赖锁版本 + UX-3 Toast 替换 alert
- **V0.7.5.6**: UX-8/9/11/12 体验批量 (AI 超时 + 报告计时 + skeleton + Calendar 友好提示)
- **V0.7.5.7**: UX-13 KB 懒加载 + UX-15 RPE onboarding
- **V0.7.5.8**: 附录 3 项 (A-2 fallback_model / A-14 KB 错误暴露 / A-15 错误不外泄)

## [V0.7.5] - 2026-08-22 — HRV / Phase / Trends / AI Coach / Reports / Sync / Diary

### Added / 新增
- **HRV** 状态分析 (Plews/Bellenger 阈值, 7d 滑动 vs 30d baseline)
- **周期化** Joe Friel 框架 (base/build/peak/taper/recovery/race) + Seiler 80/20 极化
- **训练趋势** TrendsPage (训练量 / 区间分布 / 指标 / 同比)
- **AI 教练** 重构 (orchestrator 6 块上下文 + RAG top-3 注入 + SSE 流式)
- **周报** ReportsPage (训练量 / 强度 / 关键事件)
- **同步框架** Strava OAuth (UI 框架到位, 实际联通 V0.7.8+)
- **训练日记** (V0.7.4.2 合并到此版): 训练感受/心情/睡眠/天气/痛点
- **比赛准备** Race Prep (training state / TSB target / 比赛类型)

## [V0.7.4.2] - 2026-08-21 — 训练日记 (后并入 V0.7.5)

### Added / 新增
- 3 张表: `TrainingDiary` + 9 字段
- 5 端点: `/api/diary` CRUD
- `DiaryPage 485 行`
- Sidebar 入口

## [V0.7.1 - V0.7.4] - 2026-08-15 ~ 2026-08-20

(V0.7 阶段累计: Phase 1-2 业务功能 + 修 3 用户反馈 + 训练日记)

## [V0.6.1] - 2026-08-26 — GC Differentiation + UX Depth / GC 差异化

### Added / 新增
- **拆 zip**: 体积透明度, 源码 1.4MB (无 KB) / KB 单独下载 155.9MB
- **海拔剖面图** (ElevationProfileChart, 爬升段自动识别 ≥10m 连续上升)
- **Pa:HR Decoupling** (心率-功率解耦, Joe Friel / Coggan, 4 档解读, 滑动趋势)
- **ACWR** (急慢性负荷比, Tim Gabbett 2016, 7d/28d TSS, 受伤风险预警)
- **GPS 地图** (Leaflet + OpenStreetMap, WGS-84 转换, 起点/终点 marker)
- **RPE 主观疲劳** (Borg CR-10, 0-10 训练学标准, 数据库自动迁移)
- **Periodization** (Joe Friel 框架, PMC 动态推导, 比赛倒推, Seiler 80/20 极化分布)
- **FTP 检测** (4 协议综合: Coggan 20min + Carmichael 8min × 2 + Morton CP 3-param + Ramp Test)
  - 多维置信度评分 (CV + NP/AP + 心率协同 + W' 合理性 + R²)
  - 浮动 s2 起点 (避免误选恢复段)
  - FTP 历史趋势图, 训练效果量化

### Changed / 变更
- PhasesPage 改造 (智能推荐完整依据 + Seiler 极化分布 + 比赛倒推)
- ActivityDetail 新增 RPE 编辑 / GPS 地图 / FTP 估算 段
- TrendsPage 集成 ACWR + RPE 趋势
- ActivityList 加 RPE 列

### License / 协议
- 主项目: MIT
- 知识库: 严格保护 (kb_source/LICENSE, 中英双语)

## [V0.6.0] - 2026-07 — GoldenCheetah Parity (Phase 1+2+3) / 对标 GoldenCheetah

### Added
- 7 区功率分布 (Coggan 配色 + 训练学 summary)
- W'bal (Skiba 模型, 30% 警戒区, 临界事件)
- MMP 功率曲线 (5/10/30/60/120/300/600/1200/3600s)
- HR 区间 (Karvonen 7 区 / Coggan 5 区兜底)
- HR 漂移 + 解耦 + 4 档解读
- 踏频 4 区
- Compare 模式 (多活动叠加)
- Trends 周/月聚合
- ACWR 计算引擎
- 31 个 mock 训练模板 + 5 种 profile
