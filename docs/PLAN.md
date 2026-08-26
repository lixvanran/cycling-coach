# 公路自行车 AI 教练 · Cycling Coach — 软件规划 v0.1

> **状态**:草案 v0.1(软件部分,硬件暂不规划)
> **定位**:把公路车训练从"经验"升级为"数据 + 智能"
> **参考风格**:`Photographer-Copilot`(本地优先 / 启动器 / 错误分类)+ `ZhangXuefeng-Agent`(模块化 agent / 工具注册 / 个体画像 / 多轮工具循环)

---

## 0. 范围界定

**本次只规划软件层**,硬件(码表 / 心率带 / 功率计 / 踏频器)统一走「数据导入」这一层:
- 短期:FIT / TCX / CSV 文件导入(覆盖 90% 训练数据)
- 长期:硬件厂商 SDK / BLE 直连(单独一阶段)

软件部分核心四块:
1. **数据解析** — FIT/TCX → 结构化指标
2. **AI 教练 Agent** — 解读 / 课程 / 追踪
3. **个体画像** — 长期记忆 + 强弱项分析
4. **报告与训练计划呈现** — 图表 + 文字

---

## 1. 战略地图(对应 PPT)

| PPT 区块 | 软件落点 |
|---|---|
| ① 训练数据散落 / 算法黑盒 | **数据归一化层** + **指标白盒解释** |
| ② 训练解读 / 课程生成 / 长期追踪 | **AI 教练 Agent**(三个核心工具) |
| ③ 短期:本地/云软件,FIT → ERG + 文字报告 | **MVP**:导入 → 报告 + 课程 |
| ④ 比赛实时战术 / 车队协同 | **V1.0+**:工具预留,不进 MVP |

---

## 2. 技术栈(对齐两个参考项目)

### 后端 — Python Sidecar(FastAPI)
| 组件 | 选择 | 参考 |
|---|---|---|
| 框架 | FastAPI + uvicorn | 两个项目共用 |
| LLM | OpenRouter(openai 兼容) | 两个项目共用 |
| 配置 | pydantic-settings | Z 项目 |
| DB | SQLite(SQLAlchemy 2.0 ORM) | Z 项目 |
| 日志 | logging + 文件 + stdout 继承启动器 | P 项目 |
| 错误分类 | 5 子类 M3Error 风格 + 任务级中断 | P 项目 |

**关键库**:
- `fitparse` — FIT 文件解析(FIT 官方推荐)
- `tcxparser` / 自写 — TCX
- `pandas` + `numpy` — 指标计算
- `scipy` — 平滑、峰值检测
- `pydantic` — 数据 schema

### 前端 — React + Vite + Tailwind
| 组件 | 选择 | 参考 |
|---|---|---|
| 构建 | Vite + TS | 两个项目共用 |
| UI | Tailwind + 苹果毛玻璃 | 两个项目共用 |
| 图表 | `recharts` 或 `echarts-for-react`(功率曲线 / 心率区间柱) | — |
| 状态 | Zustand(比 P 项目多一点复杂度) | Z 项目 |
| 路由 | 手写单页(对齐两个项目) | — |
| 流式 | SSE + 内嵌事件标签 | Z 项目 |
| 上传 | XHR(拿真实进度) | P 项目 |
| 桌面壳(预留) | Tauri 2 | P 项目(预留不启用) |

### 一键启动 / 诊断
- `启动.bat` / `start.sh` / `start.py` — 跨平台
- `停止.bat` / `stop.py` — 杀端口兜底
- `诊断.bat` / `diagnose.py` — 收集日志
- 镜像源 / 跨平台 shim 细节 — 抄 P 项目

---

## 3. 目录结构(融合两家之长)

```
cycling-coach/
├── README.md
├── 启动.bat / 停止.bat / 诊断.bat
├── start.sh / start.py / stop.py / diagnose.py
├── .env.example
│
├── backend/                              # Python FastAPI Sidecar
│   ├── pyproject.toml / requirements.txt
│   ├── main.py                            # FastAPI 入口 + lifespan
│   ├── core/
│   │   ├── config.py                      # pydantic-settings
│   │   └── logging.py                     # 统一日志格式
│   │
│   ├── parsers/                           # 数据解析层
│   │   ├── fit_parser.py                  # FIT → 标准化 Activity
│   │   ├── tcx_parser.py
│   │   ├── csv_parser.py                  # Garmin / Wahoo / 第三方导出
│   │   └── schema.py                      # 统一 Activity / Sample / Lap 模型
│   │
│   ├── metrics/                           # 指标计算层(白盒,核心)
│   │   ├── power.py                       # NP, IF, TSS, W', FTP 估算
│   │   ├── hr.py                          # 心率区间 / HR drift / HRT
│   │   ├── cadence.py
│   │   ├── pacing.py                      # 速度 / 配速
│   │   ├── intervals.py                   # 间歇识别(峰值检测)
│   │   ├── curve.py                       # 功率曲线(MMP)
│   │   └── aggregator.py                  # 聚合多节训练
│   │
│   ├── profile/                           # 个体画像(Z 项目 RAG 思路)
│   │   ├── model.py                       # Athlete / 训练史 / 强弱项
│   │   ├── builder.py                     # 从历史活动构建画像
│   │   ├── strengths.py                   # 强项/弱项分析(爬坡/冲刺/TT/耐力)
│   │   └── store.py                       # SQLite CRUD
│   │
│   ├── coach/                             # AI 教练 Agent(Z 项目模块化)
│   │   ├── orchestrator.py                # 总编排
│   │   ├── routing/
│   │   │   ├── classifier.py              # 任务复杂度(解读/课程/追踪)
│   │   │   ├── tier_router.py             # low/mid/high
│   │   │   └── model_whitelist.py
│   │   ├── llm/
│   │   │   ├── base.py
│   │   │   ├── openrouter.py
│   │   │   └── vision.py                  # 训练截图 / 数据图
│   │   ├── tools/                         # ⭐ 核心:三个工具 + 周边
│   │   │   ├── registry.py
│   │   │   ├── analyze_activity.py        # 解读单次训练
│   │   │   ├── generate_workout.py        # ERG 课程生成
│   │   │   ├── track_progress.py          # 长期追踪 / 强弱项
│   │   │   ├── erg.py                     # ERG 文本/ZWO 输出
│   │   │   └── athlete_qa.py              # 问教练(SSE 流式)
│   │   ├── prompts/
│   │   │   ├── builder.py
│   │   │   ├── style.py                   # 教练语气
│   │   │   └── scenarios/
│   │   │       ├── analyze.py
│   │   │       ├── generate.py
│   │   │       └── track.py
│   │   └── pipeline/
│   │       ├── context_builder.py         # system + athlete profile + activity
│   │       ├── llm_runner.py              # 多轮工具循环(对齐 Z 项目)
│   │       └── postprocessor.py
│   │
│   ├── reports/                           # 报告生成
│   │   ├── markdown_report.py             # 单次训练报告
│   │   ├── weekly_summary.py
│   │   └── charts.py                      # matplotlib → png → base64
│   │
│   ├── db/
│   │   ├── database.py                    # ORM + schema 迁移
│   │   └── models.py                      # Activity / Athlete / Workout / ...
│   │
│   └── routers/
│       ├── activities.py                  # 导入 / 列表 / 详情
│       ├── workouts.py                    # 课程生成 / ERG 导出
│       ├── athlete.py                     # 画像
│       ├── coach.py                       # 问教练(SSE)
│       └── diagnose.py
│
├── frontend/
│   ├── package.json + pnpm-workspace.yaml
│   ├── vite.config.ts / tailwind.config.js
│   ├── index.html
│   └── src/
│       ├── main.tsx / App.tsx
│       ├── pages/
│       │   ├── DashboardPage.tsx          # 训练概览(本周 / 趋势)
│       │   ├── ActivityPage.tsx           # 单次训练详情 + AI 报告
│       │   ├── ImportPage.tsx             # 导入 FIT/TCX
│       │   ├── WorkoutPage.tsx            # ERG 课程生成 + 预览 + 下载
│       │   ├── CoachPage.tsx              # SSE 流式问教练
│       │   └── ProfilePage.tsx            # 画像 / FTP / 强弱项
│       ├── components/
│       │   ├── Sidebar.tsx
│       │   ├── UploadButton.tsx           # XHR 进度
│       │   ├── TaskProgress.tsx
│       │   ├── PowerCurve.tsx             # recharts
│       │   ├── HRZoneBar.tsx
│       │   ├── WorkoutPreview.tsx         # ERG 区间预览
│       │   └── ChatBox.tsx                # SSE 流式
│       ├── lib/
│       │   ├── api.ts
│       │   ├── api-types.ts
│       │   └── usePersistedState.ts
│       └── store/useAppStore.ts           # Zustand
│
├── src-tauri/                             # 预留(对齐 P 项目,暂不启用)
│
├── scripts/
│   ├── smoke_test.py                      # 端到端冒烟
│   └── sample_fit/                        # 示例 FIT 文件
│
├── knowledge_base/                        # 教练领域知识
│   ├── training_zones.json                # 训练区间定义
│   ├── workout_templates.json             # ERG 课程模板库
│   ├── periodization.json                 # 周期化训练规则
│   └── coach_persona.json                 # 教练语气 / 价值观
│
├── workspace/                             # 运行时数据(gitignore)
│   ├── input/                             # 用户丢 FIT
│   ├── output/                            # 报告 / 课程
│   ├── .logs/
│   └── cycling_coach.sqlite
│
└── docs/
    ├── PLAN.md                            # 本文档
    ├── ARCHITECTURE.md
    └── METRICS.md                         # 指标定义 + 计算公式
```

---

## 4. 数据模型(核心表)

```sql
-- 运动员(单用户 MVP)
athlete (
  id, name, ftp, ftp_estimated, max_hr, lthr,
  weight_kg, height_cm, created_at, updated_at
)

-- 单次训练
activity (
  id, athlete_id, source ('fit'|'tcx'|'csv'),
  start_time, duration_s, distance_m,
  avg_power, normalized_power, intensity_factor, tss,
  avg_hr, max_hr, avg_cadence,
  total_elevation_gain, avg_speed,
  raw_path,                       -- 原始文件路径(可重新解析)
  parsed_json_path,               -- 解析后结构化 JSON
  status ('imported'|'analyzed'|'failed'),
  created_at
)

-- 训练样本(1Hz 抽样,存 SQLite 太重,改用 parquet/SQLite blob)
-- MVP 阶段先在内存,后续优化
-- activity_sample (activity_id, t_offset, power, hr, cadence, speed, elevation, lat, lon)

-- Lap / 间歇
activity_lap (
  id, activity_id, start_offset, duration_s,
  avg_power, avg_hr, label, type ('warmup'|'interval'|'recovery'|...)
)

-- 强弱项快照(定期 / 每次分析后)
strength_snapshot (
  id, athlete_id, computed_at,
  climb_score, sprint_score, tt_score, endurance_score,
  threshold_score, evidence_json
)

-- AI 生成的训练课程
workout (
  id, athlete_id, activity_id NULL,        -- 是否基于某次训练
  title, goal, duration_min,
  structure_json,                           -- [{type, duration_s, power_pct_ftp, hr_zone}, ...]
  erg_text,                                 -- ERG 原始文本
  zwo_path,                                 -- 导出的 ZWO 文件
  created_at
)

-- 教练对话
conversation / message(对齐 Z 项目)

-- 用户偏好(对齐 Z 项目)
user_preferences (key, value_json)
```

---

## 5. 核心模块详细设计

### 5.1 解析层 `parsers/`

**目标**:不同来源 → 统一 `Activity` schema。

`fitparse` 是 FIT 官方推荐,支持 Record / Lap / Session 完整解析。

**统一 schema**(Pydantic):
```python
class Sample(BaseModel):
    t_offset: int           # 秒
    power: int | None
    hr: int | None
    cadence: int | None
    speed: float | None     # m/s
    elevation: float | None
    lat: float | None
    lon: float | None

class Lap(BaseModel):
    start_offset: int
    duration_s: int
    avg_power: int | None
    avg_hr: int | None
    label: str | None
    type: str               # 'warmup' | 'interval' | ...

class Activity(BaseModel):
    source: str
    start_time: datetime
    duration_s: int
    distance_m: float
    samples: list[Sample]   # 1Hz 抽样
    laps: list[Lap]
    device: str | None
    raw_meta: dict
```

### 5.2 指标层 `metrics/`

**对齐 PPT 提到的**:功率、心率、踏频、FTP、功率曲线。

| 指标 | 公式/算法 | 说明 |
|---|---|---|
| **平均功率** | mean(samples.power) | 简单 |
| **归一化功率 NP** | 30s 滑窗 → 4 次方 → 平均 → 开 4 次方 | Coggan |
| **IF** | NP / FTP | |
| **TSS** | (duration_s × NP × IF) / (FTP × 3600) × 100 | |
| **W' 消耗** | 积分 W'bal 模型 | 高级,MVP 可先占位 |
| **HR drift** | 后半段 HR - 前半段 HR | 有氧基础参考 |
| **HRT (HRT-decoupling)** | 同上但用功率做分母 | |
| **心率区间时间分布** | 5 区累计秒数 | |
| **踏频** | mean / 区间分布 | |
| **配速** | distance / duration | |
| **爬坡得分** | 4%+ 坡度段的 W/kg 表现 | |
| **间歇识别** | scipy find_peaks(功率/HR) + lap 对齐 | |
| **功率曲线 MMP** | 每个时长的 max avg power | 1s, 5s, 30s, 1min, 5min, FTP, ... |
| **FTP 估算** | 20min 最佳 × 0.95 / 8min 最佳 × 0.90 | 当用户没手动设 |

`metrics/aggregator.py`:多文件批量算 → 入库。

### 5.3 个体画像 `profile/`

**对齐 Z 项目的 RAG/记忆**思路,这里是「训练画像」:

```python
class AthleteProfile(BaseModel):
    identity: dict                  # 基础信息
    ftp_history: list[(date, ftp)]  # FTP 演变
    strengths: dict                 # {climb, sprint, tt, endurance, threshold}
    training_load: dict             # CTL/ATL/TSB(Fitness/Fatigue/Form)
    preferences: dict               # 训练日 / 目标赛事 / 课程偏好
    injury_history: list             # 伤病记录
```

**`strengths.py`**:
- 基于过去 90 天活动聚合:爬坡段 W/kg、冲刺段 W、TT 段 W/kg、Z2 耐力
- 给出每项 0-100 分 + 证据(哪几次活动)
- 每次新活动入库后增量更新

### 5.4 AI 教练 Agent `coach/`

**对齐 Z 项目模块化 agent**:

```
用户问题 / 触发
  ↓
orchestrator.process_message
  ↓
routing.classifier.classify(analyze|generate|track|chat)
  ↓
tier_router.route(tier)
  ↓
context_builder.build(system + athlete profile + activity context)
  ↓
llm_runner.run_with_tools(messages, tools, max_rounds=3)
  ↓ (多轮工具循环)
tools.execute(*)
  ↓
postprocessor.clean + persist
  ↓
SSE stream → 前端
```

**三个核心工具**:

1. **`analyze_activity(activity_id, focus)`**
   - 输入:活动 ID + 用户关注点(可选)
   - 执行:拉取 activity + 计算关键指标 + 查个体画像
   - 输出:结构化 `{summary, highlights, issues, recommendations, training_load_impact}`

2. **`generate_workout(goal, duration_min, constraints)`**
   - 输入:目标(爬坡/冲刺/恢复/...)+ 时长 + 约束(今天 TSS 限制 / 设备功率上限)
   - 执行:查个体画像 + 查 workout_templates 库 + 组装
   - 输出:`Workout` 结构 + ERG 文本 + ZWO 文件

3. **`track_progress(period)`**
   - 输入:周期(week/month/season)
   - 执行:聚合活动 + 算训练负荷 + 强弱项对比
   - 输出:趋势报告 + 强项弱项变化 + 建议

**教练 persona**(`prompts/style.py`):
- 不灌鸡汤,数据说话
- 直白但不刻薄(对齐 Z 项目张雪峰风格,但更温和)
- 短句多,善用对比(「这次 NP 比上次涨了 8W,但 HR 反而低 5bpm,有氧基础在进步」)

### 5.5 报告层 `reports/`

- **单次训练报告**:Markdown + 关键指标卡 + 功率曲线图 + 心率区间图
- **周报**:CTL/ATL/TSB 趋势 + 本周完成情况 + 下周建议
- **导出**:PDF(可选) / Markdown / HTML

---

## 6. 关键流程

### 6.1 导入 + 解读

```
用户拖 FIT → UploadButton(XHR 进度)
  → POST /api/activities/upload
  → 落盘 workspace/input/<时间>-uploaded/
  → 后端异步:
     1. parsers/fit_parser 解析 → Activity
     2. metrics/* 计算 → 入库
     3. profile/builder 更新画像
     4. coach/tools/analyze_activity 自动生成报告
  → SSE 推送 progress → 前端 TaskProgress
  → 完成 → 跳转 ActivityPage
```

### 6.2 生成 ERG 课程

```
用户在 WorkoutPage:
  选目标(爬坡) + 时长(60min) + 日期
  → POST /api/workouts/generate
  → 同步返回(用时秒级)+ 异步细化(可选,带历史)
  → 预览(分段时间轴 + 功率条 + 心率区)
  → 点「下载 .zwo」→ 直接给文件
  → 点「发给码表」→ V1.0+ 通过 BLE/USB
```

### 6.3 问教练(对齐 Z 项目 SSE)

```
CoachPage 提问
  → POST /api/coach/chat (SSE)
  → 后端 orchestrator → llm_runner(可能多轮工具调用)
  → 流式 yield [THINKING]...[/THINKING] [TOOL_CALL]...[/TOOL_CALL] [TEXT]...[/TEXT]
  → 前端 ChatBox 解析 + 渲染
```

---

## 7. 分阶段路线图

### V0.1 — MVP(2-3 周)
- [ ] 项目骨架 + 启动器(抄 P 项目)
- [ ] FIT 解析 + 基础指标(NP/IF/TSS/HR/踏频)
- [ ] 导入页 + 活动详情页
- [ ] 功率曲线 / 心率区间图
- [ ] 个体画像雏形(FTP + 训练史)
- [ ] **analyze_activity 工具** + 文字报告
- [ ] M3 mock 模式(对齐 P 项目)

### V0.2 — 课程生成
- [ ] generate_workout 工具
- [ ] ERG 文本 + ZWO 文件导出
- [ ] WorkoutPage 预览
- [ ] workout_templates 知识库

### V0.3 — 长期追踪
- [ ] track_progress 工具
- [ ] 强弱项分析 + Dashboard
- [ ] 周报 / 月报
- [ ] CTL/ATL/TSB

### V0.4 — 多轮对话
- [ ] CoachPage(SSE 流式)
- [ ] athlete_qa 工具
- [ ] 多轮工具循环(对齐 Z 项目)
- [ ] 路由分层(low/mid/high)

### V1.0 — 完善
- [ ] TCX / CSV 解析
- [ ] 周期化训练规则
- [ ] 报告 PDF 导出
- [ ] 详细错误分类(对齐 P 项目 M3Error 5 子类)
- [ ] 完整 README + 故障排查

### V1.1+ — 硬件接入(后续单独规划)
- [ ] 码表 BLE/USB
- [ ] 心率带 / 功率计
- [ ] 比赛实时战术
- [ ] 车队级协同

---

## 8. 设计原则(对齐两个参考项目的工程文化)

1. **详细中文注释 + 顶层 docstring** — 写清楚「这个模块做什么 + 当前版本 + 未来扩展点」
2. **版本号语义化** — README 写「v0.X.Y 升级要点」,每个修复留痕(`# v0.X.Y 修复: ...`)
3. **错误分类 + 任务级中断** — 401/402/网络错 break,5xx 重试 1 次,per-photo 失败不算任务失败
4. **Mock 模式 first-class** — 没 key 也能跑通 demo + smoke test
5. **本地优先** — 训练数据不离开电脑,LLM 只看聚合指标 / 抽样数据
6. **SSE 事件回放 + pending_start 握手** — 解决前后端启动竞态
7. **路径安全** — `_sanitize_rel_path` 严防路径穿越
8. **白名单 + 兜底校验** — 模型选型三层防御
9. **零依赖兜底** — 没 OpenAI key 用 TF-IDF(对齐 Z 项目)
10. **隐私** — 原 FIT 永远不删,产物走非破坏性

---

## 9. 风险与待定项

| 风险 | 应对 |
|---|---|
| FIT 解析器 1Hz 抽样太密,SQLite 存不下 | 存 parquet / 二级存储,DB 只存聚合 |
| 1Hz 数据传给 LLM 太大 | 喂 LLM 前降采样(30s/5min 聚合)+ 关键区间抽样 |
| 教练建议需要专业准确性 | 训练学规则用 `knowledge_base/`,LLM 只做「人话翻译」 |
| 个体画像冷启动(新用户) | 提示「至少导入 5 次训练再生成课程」 |
| ERG 课程生成质量 | MVP 先用模板匹配 + 参数化,LLM 做组合而非发明 |
| 多档路由是否需要(MVP 阶段) | V0.4 再说,MVP 单档够用 |

---

## 10. 我现在不会做的事(等你拍板)

1. ❌ 暂不动代码
2. ❌ 暂不建 GitHub 仓库
3. ⏳ 等你确认这份规划后,我会:
   - 先出 V0.1 骨架 zip 预览(对齐你的工作流)
   - 你点头后,初始化项目 + 推 GitHub
4. ❓ 想听你拍板的:
   - **项目名**:`cycling-coach` / `cycling-ai-coach` / 其他?
   - **MVP 范围**:V0.1 这一刀够不够小?要不要再砍?
   - **图表库**:`recharts`(轻) / `echarts`(重但强) / 倾向?
   - **目标用户**:纯自用 / 给车队用 / 公开工具?影响后续架构
   - **数据源**:先只做 FIT,还是 TCX 一起?TCX 解析量不大,可以一起做
