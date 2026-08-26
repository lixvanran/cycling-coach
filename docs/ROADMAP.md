# Cycling Coach Roadmap / 路线图

> Last updated: 2026-08-26 (V0.6.1 release)

## ✅ Released (已发布)

### V0.5 — Knowledge Base Foundation
- ✅ 训练百科 (Training Encyclopedia) 集成, 359 docs / 500 chunks / 252 attachments
- ✅ RAG 自动注入 (kb_chunks 表 + FTS5 全文索引)
- ✅ MIT + KB Restricted 双协议 (dual license)

### V0.5.1 — UX Optimization
- ✅ BuilderPage scratch-style drag-drop
- ✅ CalendarPage popover + drag
- ✅ KB tree + 热门标签
- ✅ 按钮饱和色 + focus ring + search highlight

### V0.5.2 — Desktop Exploration
- ✅ PyInstaller + Electron 探索
- ✅ Dev mode (一键启动 + 浏览器)

### V0.5.3 — Desktop App (Code Reserved)
- ✅ Electron + electron-builder NSIS 配置
- ✅ PyInstaller spec 完整
- ⚠️ 桌面应用闪退,代码预留,dev 模式为一键启动方案

### V0.6.0 — GoldenCheetah Parity (Phase 1+2+3)
- ✅ Power Zones 7 区 (Coggan 配色)
- ✅ W'bal (Skiba 模型) + 30% 警戒区
- ✅ CP 3-param (Morton 1996) + W' + R²
- ✅ ComparePage (多活动对比, 16 指标, MMP 叠加)
- ✅ TrendsPage (4 段: 训练量 / 7区 / 指标 / PMC)

### V0.6.1 — GC Differentiation + UX Depth
- ✅ **拆 zip**: source 1.4MB + kb 155.9MB (体积透明)
- ✅ **海拔剖面图** (ElevationProfileChart, 爬升段识别)
- ✅ **Pa:HR Decoupling** (EF 滑动, 4 档解读, Joe Friel / Coggan)
- ✅ **ACWR** (7d/28d, Gabbett 2016, 0.8-1.3 安全区)
- ✅ **GPS 地图** (Leaflet + OpenStreetMap, WGS-84)
- ✅ **RPE 主观疲劳** (Borg CR-10, 0-10 训练学)
- ✅ **Periodization** (PMC 推导 + 比赛倒推 + Seiler 80/20)
- ✅ **FTP 检测** (Coggan 20min + Carmichael 8min + Morton CP3 + Ramp, 4 协议综合)

## 🚧 In Progress (进行中)

- 🔄 GitHub 开源 (MIT 主 + 知识库受限, 中英双语)
- 🔄 桌面应用重新评估 (用户决定)

## 📋 Planned (规划中)

### V0.7 — Automation & Insights
- [ ] 自动周报 PDF (图表 + 文字 + 训练学解读)
- [ ] HRV 趋势 (RMSSD 7天滑动, 跟 ACWR 联动)
- [ ] 自动洞察告警 (TSS 突增, IF 持续高, ACWR 危险区间)
- [ ] AI 训练建议生成 (综合 FTP+ACWR+周期+RPE)
- [ ] Periodization 自动检测 (基于 TSS 趋势, 替代手动)

### V0.8 — Integration & Sync
- [ ] Strava 同步 (OAuth, 增量拉取活动)
- [ ] Garmin Connect 同步 (可选, 需用户授权)
- [ ] Calendar 集成 (Google Calendar / iCal, 比赛日同步)
- [ ] Wahoo / Garmin 训练台控制

### V0.9 — Advanced Analytics
- [ ] AeroLab (空气动力学分析, CdA 估算)
- [ ] 营养/恢复追踪 (睡眠, 主观疲劳, 体重, 蛋白摄入)
- [ ] 多人 / 教练视图 (一个教练带多个运动员)
- [ ] 训练计划市场 (教练可发布计划, 用户订阅)

### V1.0 — Stable Release
- [ ] 性能优化 (大文件 FIT 解析, 大数据量图表)
- [ ] 国际化 (i18n, 至少 EN/中/日/西)
- [ ] 跨平台桌面 (Windows / macOS / Linux)
- [ ] 移动端 (iOS / Android, 离线优先)
- [ ] 云同步 (可选, 端到端加密)

## 🚫 Out of Scope (不做)

- ❌ 实时 ANT+ 训练台连接 (硬件支持需大量工作)
- ❌ 云端存储 (用户隐私优先, 数据本地化)
- ❌ 商业交易平台 (训练百科作者选择不开)

## Timeline (时间表)

| Version | Target     | Status        |
|---------|------------|---------------|
| V0.5.x  | 2026-04    | ✅ Released   |
| V0.6.0  | 2026-07    | ✅ Released   |
| V0.6.1  | 2026-08    | ✅ Released   |
| V0.7    | 2026-10    | 🚧 In Progress |
| V0.8    | 2026-12    | 📋 Planned    |
| V0.9    | 2027-Q1    | 📋 Planned    |
| V1.0    | 2027-Q2    | 📋 Planned    |

## Contributing / 贡献

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the dual-license contribution policy.
参见 [CONTRIBUTING.md](../CONTRIBUTING.md) 了解双协议贡献政策。

## License / 许可证

- Code: MIT — [LICENSE](../LICENSE) | [LICENSE.zh-CN](../LICENSE.zh-CN)
- Knowledge Base: Restricted — [kb_source/LICENSE](../kb_source/LICENSE)
