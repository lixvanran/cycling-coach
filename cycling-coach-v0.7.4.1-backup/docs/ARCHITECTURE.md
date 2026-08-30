# Cycling Coach 架构 (V0.7.4)

> 当前状态: V0.7.4 (2026-08-28)
> 历史 V0.2.0 段已折叠, 仅作参考

---

## 0. 当前状态 (V0.7.4)

### 0.1 技术栈
- **后端**: Python 3.11+ / FastAPI 0.141 / SQLAlchemy 2.0 / SQLite / reportlab 5.0
- **前端**: React 18 / Vite 5 / Recharts / Tailwind / Zustand / lucide-react
- **桌面**: V0.5.3 搁置 (闪退), dev 模式 + 浏览器
- **AI**: OpenRouter 兼容协议 (M3 model = minimax-m3)

### 0.2 端点 (V0.7.4: 87 端点 / 99 method)
| 模块 | 路径前缀 | 端点数 | 职责 |
|------|----------|--------|------|
| activities | /api/activities | 10 | 活动 CRUD + 分析 + 同步 |
| athlete | /api/athlete | 2 | 运动员档案 |
| calendar | /api/calendar | 8 | 日历 + 计划 + 排课 |
| coach | /api/coach | 1 | AI 对话 (SSE) |
| dashboard | /api/dashboard | 1 | 首页总览 |
| ftp | /api/ftp | 4 | FTP 估计/历史/复测 |
| hrv | /api/hrv | 3 | HRV 趋势 (V0.7.2) |
| insights | /api/insights | 1 | 训练洞察 |
| kb | /api/kb | 1 | 知识库 |
| phases | /api/phases | 8 | 周期化 (V0.6.1) + 7 比赛类型 (V0.7.1) |
| plans | /api/plans | 1 | 训练计划 |
| pmc | /api/pmc | 1 | PMC (CTL/ATL/TSB) |
| race_prep | /api/race-prep | 1 | 比赛准备 |
| recommendations | /api/recommendations | 2 | AI 训练建议 (V0.7.3) |
| reports | /api/reports | 1 | 周报 PDF (V0.7.3) |
| sync | /api/sync | 5 | Strava 同步预留 (V0.7.4) |
| trends | /api/trends | 1 | 趋势分析 |
| workouts | /api/workouts | 16 | 课程 CRUD + 5 格式导出 |
| diagnose | /api/diagnose | 1 | 自诊断 |
| dev | /api/dev | 2 | 开发工具 (仅 dev_mode) |

### 0.3 后端目录 (V0.7.4)
```
cycling_coach/
├── __init__.py             # 版本 SSOT (V0.7.4)
├── _version.py             # 版本号加载 (importlib.metadata → tomllib)
├── __main__.py             # python -m cycling_coach
├── ai/                     # AI 层
│   ├── orchestrator.py     # RAG + chat 编排 (V0.7.1 Grok 修订)
│   ├── prompts/chat.py     # 训练学上下文 6 块 (V0.7.1)
│   └── client.py
├── api/                    # HTTP 层
│   ├── main.py             # FastAPI app, 21 router 注册, /api/version
│   ├── routers/            # 19 个 router, 纯 HTTP
│   │   ├── activities.py   # 872 行
│   │   ├── workouts.py     # 901 行
│   │   ├── phases.py       # 421 行
│   │   ├── ftp.py          # 368 行
│   │   ├── trends.py       # 367 行
│   │   ├── ... (15 个)
│   │   └── sync.py         # V0.7.4 Strava 预留
│   └── frontend.py         # 静态资源
├── config/                 # 配置
│   └── config.py           # Settings, dev_mode 默认 False
├── core/                   # 业务逻辑层
│   ├── pmc.py              # PMC 计算 (CTL/ATL/TSB)
│   ├── profile/            # 运动员档案
│   ├── kb_downloader.py    # 训练百科下载
│   ├── kb_importer.py      # 知识库导入
│   ├── metrics/            # 学术算法 (核心)
│   │   ├── power.py        # NP/IF/TSS/W'bal (V0.7.4 升级 Skiba 2012)
│   │   ├── acwr.py         # ACWR (Gabbett 2016)
│   │   ├── hrv.py          # HRV (Plews 2013)
│   │   ├── ftp.py          # FTP 5 算法
│   │   ├── periodization.py# 周期化 (Friel CTB) + 6 信号
│   │   ├── insights.py     # 训练洞察
│   │   ├── race_prep.py    # 7 比赛类型
│   │   ├── curve.py        # 功率曲线
│   │   ├── hr.py           # HR 区间
│   │   └── aggregator.py   # 指标聚合
│   ├── coaching/           # 训练教练
│   │   └── recommendations.py  # V0.7.3 综合 5 维
│   ├── reports/            # 报告
│   │   └── weekly.py       # V0.7.3 PDF (reportlab)
│   ├── exporters/          # 课程导出 (5 格式)
│   │   ├── zwo.py          # Zwift XML
│   │   ├── mrc.py          # Rouvy
│   │   ├── erg.py          # CompuTrainer
│   │   ├── fit.py          # V0.7.4 Garmin/Wahoo
│   │   └── json.py
│   └── sync/               # 第三方同步 (V0.7.4 预留)
│       ├── base.py         # SyncProvider abstract
│       └── strava.py       # Strava 接口骨架
├── data/                   # 数据层
│   ├── sqlite/             # ORM (models.py) + database
│   └── parsers/            # 数据解析
│       ├── fit_parser.py   # .fit
│       ├── tcx_parser.py   # .tcx (V0.7.1)
│       └── csv_parser.py   # WKO CSV (V0.7.1)
├── static/                 # 前端 build 产物 (Vite → 1.119MB)
└── worker/                 # Worker (预留)
```

### 0.4 测试 (V0.7.4: 41 passed)
- `tests/unit/test_metrics.py` — 14 个, 7 区/HR 区间/功率曲线/HR drift/cadence
- `tests/test_power.py` — 13 个, NP/IF/TSS/W'bal/Coggan 20min
- `tests/test_acwr.py` — 4 个, ACWR 空/恒定/ramp up/ramp down
- `tests/test_ftp.py` — 3 个, FTP 5 方法 + max_hr/lthr
- `tests/test_wbal_skiba.py` — V0.7.4 新加 7 个, 严格 Skiba 2012 differential 物理性

### 0.5 算法 (V0.7.4 严格化)
- **NP** (Normalized Power): Coggan 2003 — 30s rolling avg + 4次方
- **IF / TSS**: NP/FTP + (dur × NP × IF) / (FTP × 3600) × 100
- **W'bal**: V0.7.4 **升级**到 Skiba 2012 strict differential, 7 个新测试
- **ACWR**: Gabbett 2016 — 7d/28d 简单均值
- **HRV**: Plews 2013 — 7d 滑动 + 30d baseline
- **Periodization**: Friel CTB — 比赛倒推 + 6 维信号
- **Polarized**: Seiler 80/20
- **HR zones**: LTH 7 区
- **Power zones**: Coggan 7 区

---

## 1. 数据流

```
[用户浏览器 1420]
    ↓ HTTP
[Vite dev server / static]
    ↓
[FastAPI 8765]
    ↓ router
[core/services 业务层 (未来)]
    ↓
[core/metrics 学术算法]
    ↓
[SQLite / KB]
```

---

## 2. 部署模式

### 2.1 Dev 模式 (当前推荐)
- 后端: `python -m cycling_coach --backend-only --no-kb-import` (端口 8765)
- 前端: Vite dev server (端口 1420)
- 启动: `tools\start.bat` (Windows) / `tools/start.sh` (macOS/Linux)

### 2.2 桌面端 (V0.5.3 搁置)
- 闪退问题未修, 暂不使用
- 路径: `apps/desktop/main.cjs` (Electron)

---

## 3. 数据安全

- MIT (代码) + Restricted (训练百科 kb_source/)
- `.env` 不进 git, 沙箱有占位 .env
- 知识库 kb 单独 zip (148MB) 走 release
- GPG 签名未启用 (V0.7.1 状态)

---

## 4. 路线图

### V0.7.4 (当前)
- ✅ W'bal 升级 Skiba 2012
- ✅ Strava 同步接口预留
- ✅ FIT 课程导出
- ✅ 架构文档整理

### V0.8+ (规划)
- Strava OAuth 实装
- Garmin Connect 同步
- 移动端响应式
- 桌面端 V0.7.x 重启 (重写 apps/desktop)

### V1.0+ (远期)
- i18n (中英双语)
- 多人教练视图
- 计划市场
- 云同步
