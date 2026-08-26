# Changelog / 变更日志

All notable changes to this project will be documented in this file.

本项目的所有重要变更都将记录在此文件中。

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased] / 下一版

### Planned / 计划
- 自动周报 PDF 生成
- HRV 趋势分析
- 自动洞察告警
- AI 训练建议生成

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
- Critical Power 3-param (Morton 1996, R² + W')
- ComparePage (多活动对比, 16 指标, MMP 叠加)
- TrendsPage (训练量/7区/指标/PMC 4 段)

## [V0.5.x] - 2026-04 → 06 — Foundation

### V0.5.0 — Knowledge Base Foundation
- 训练百科集成 (359 docs / 500 chunks / 252 attachments)
- RAG 自动注入 (SQLite FTS5 + Embedding 预留)
- 双协议 (MIT + KB Restricted) 首次确立

### V0.5.1 — UX Optimization
- BuilderPage scratch-style drag-drop
- CalendarPage popover + drag
- KB tree + 热门标签

### V0.5.2 — Desktop Exploration
- PyInstaller + Electron 探索
- Dev mode (`tools/start.bat`)

### V0.5.3 — Desktop App (Code Reserved)
- Electron + electron-builder NSIS 配置
- 桌面应用闪退 → 代码预留, dev 模式为一键启动方案

## License / 协议

This changelog file is part of Cycling Coach, licensed under MIT.
See [LICENSE](LICENSE) for details.

本变更日志是 Cycling Coach 项目的一部分,采用 MIT 协议授权。
详见 [LICENSE](LICENSE)。
