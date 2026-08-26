# 公路自行车 AI 教练 · Cycling Coach

> 把公路车训练从"经验"升级为"数据 + 智能"。

![Version](https://img.shields.io/badge/version-v0.6.1-blue.svg)
![Status](https://img.shields.io/badge/status-V0.6.1--GC%20Differentiation-green.svg)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![React](https://img.shields.io/badge/react-18-61dafb)
![License: Dual (MIT + KB Restricted)](https://img.shields.io/badge/license-Dual%20(MIT%20%2B%20KB%20Restricted)-blue)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/lixvanran/cycling-coach)
![GitHub stars](https://img.shields.io/github/stars/lixvanran/cycling-coach)
![GitHub issues](https://img.shields.io/github/issues/lixvanran/cycling-coach)

## 当前版本: **V0.6.1** — 对标 GoldenCheetah (GC 差异化)

> ⚠️ **双协议 (Dual License)**
> - **软件代码** (MIT) — [LICENSE](LICENSE) | [LICENSE.zh-CN](LICENSE.zh-CN)
> - **知识库** `kb_source/` (Restricted by 潘震(公路车教练)) — [kb_source/LICENSE](kb_source/LICENSE)
>
> 训练百科内容来源: **潘震(公路车教练)**, 仅供本地 RAG 检索, 禁止再分发/衍生/商用

### V0.6 阶段一览

| 版本 | 重点 | 状态 |
|------|------|------|
| V0.6.0 | 7 区功率 + W'bal + CP 3-param + Compare + Trends | ✅ |
| V0.6.1 | Pa:HR Decoupling + ACWR + GPS + 海拔 + RPE + 周期化 + FTP 4 协议 | ✅ |

### V0.4 → V0.5 升级要点

- 📚 **知识库 — 把教练 10 年经验装进 AI 脑子里**
  - 来源:**潘震(公路车教练)**(原网站 SPA 1:1 离线整理,授权转载)
  - 体量:**8 顶层分类 + 训练百科 1-10 章 + 359 篇文档 + 500 个 RAG 切片 + 252 张训练示意图**
  - 内容覆盖:训练概述 / 训练方法(功率·心率·室内) / 训练执行(七部曲·规划·误区) / 车下训练(力量·核心) / 运动人体科学(营养·恢复) / 训练工具与装备 / 训练常见问题 / 常用训练资源 / 高级训练知识 / 青少年专题 / 执教知识 / 教练随笔 / 竞技百科 / 专业术语
- 🔍 **浏览 + 搜索 + AI 检索三件套**
  - 浏览:左侧分类树 → 右侧 markdown 文档(图片/列表/代码块全支持)
  - 搜索:SQLite FTS5 全文索引 + `<mark>` 高亮
  - AI 检索:问 AI 时自动 top-3 chunks 注入 system prompt
- 🔮 **Embedding 预留** — `kb_chunks.embedding BLOB + embedding_model` 字段已建,V0.5.1 接向量检索时直接填
- 🛠️ **自动迁移 / 自动导入** — 首次启动自动跑,后续秒起

### V0.1.0-V0.4 累计实现(完整功能集)

- FIT 解析(`fitparse` + 1Hz 样本入库)
- 核心指标:NP / IF / TSS / EF / VI / W'bal / MMP / HR 区间(Karvonen 7 区 / 5 区兜底)/ HR 漂移 / 踏频 4 区 / 功率 Coggan 7 区
- AI 教练:OpenRouter 兼容协议 + reasoning model 支持 + 5 类错误分类 + m3 → m2.7 fallback + **RAG 知识库自动注入**
- SSE 流式对话(带思考过程折叠)
- SQLite 本地存储 + SQLAlchemy 2.0
- 训练计划 + 课程库(29 系统课 + scratch 搭积木) + 训练日历(自动关联)
- 功率曲线 (MMP) + 训练多维过滤(日期/距离/TSS/NP/功率/时长/心率) + 排序 + 分页
- 跨平台一键启动 + GBK 编码兼容

### V0.5 后端 (Python + FastAPI)

- [x] **知识库导入器** — `core/kb_importer.py`,自动跑,增量支持
- [x] **FTS5 全文索引** — SQLite 虚拟表 + unicode61 中文分词
- [x] **RAG 检索** — `ai/orchestrator.py: _retrieve_kb()` 自动 top-3 chunks
- [x] **AI 教练** — OpenRouter 兼容协议(minimax M3 + m2.7 fallback)
  - 支持 reasoning model(`delta.reasoning` 抽取思考过程)
  - 5 类错误分类(401 / 402 / 5xx / 网络 / 解析)
- [x] **Embedding 字段预留** — `kb_chunks.embedding BLOB` + `embedding_model`
- [x] **多场景 prompt** — 解读训练 / 自由对话 / 知识库参考(自动 RAG 注入)
- [x] **流式响应** — SSE,前端实时渲染
- [x] **本地数据库** — SQLite + SQLAlchemy 2.0(数据不离开电脑)
- [x] **10 个 REST 模块** — activities / athlete / dashboard / dev / coach / pmc / plans / calendar / workouts / **kb**
- [x] **冒烟测试** — `scripts/smoke_test.py` 端到端跑通

### V0.5 前端 (React + Vite + Tailwind)

- [x] **10 个页面** — Dashboard / 日历 / 训练列表 / 训练详情 / 导入 / 个人画像 / AI 教练 / **课程库 / 课程编排 / 知识库**
- [x] **5+1 类图表** — 功率曲线 / 心率区间 / 功率-心率-海拔时间图 / 周柱状 / 表格 / PMC
- [x] **AI 教练对话** — 用户/AI 气泡、SSE 流式、停止按钮、思考过程折叠、Markdown 渲染 + RAG 检索结果可点
- [x] **课程编辑器 (scratch 搭积木)** — 基础积木 + 循环积木 + 快速模板 + 顶部/底部双保存按钮
- [x] **训练计划** — 周/日训练规划 + 自动关联实际活动 + 完成度统计
- [x] **5 个 Mock 训练模板** — 无 FIT 文件也能完整体验
- [x] **知识库浏览** — 树形导航 + 全文搜索 + Markdown 渲染 + 附件网格

### V0.5 工程

- [x] **跨平台一键启动** — Windows `.bat` + macOS/Linux `.sh`(沙盒内验证通过)
- [x] **GBK 编码兼容** — Windows 启动器自动 UTF-8,无解码错误
- [x] **直接调 `node_modules/.bin/vite`** — 避免 pnpm + 中文路径兼容性坑
- [x] **老库自动迁移** — workouts / kb_chunks 表加新列 / 老 schema 兼容(无需重置数据)
## 30 秒上手

Windows:解压后双击 `tools\start.bat`,等 1-2 分钟,看到「应用已就绪」后浏览器开 `http://localhost:1420`。

macOS / Linux:
```bash
./tools/start.sh
```

启动脚本会自动装 Python venv + Node 依赖、配 pip / npm 镜像源、起后端 + 前端。

停止:`tools\stop.bat` 或 `./tools/stop.sh`

## 第一次体验流程

1. 打开 `http://localhost:1420`
2. 进入「导入」页面
3. 点「Z2 长距离 90min」生成一个模拟活动
4. 自动跳到「训练详情」,看到:
   - 功率 / 心率 / 海拔 实时图
   - 功率曲线 (MMP)
   - HR 区间分布
   - AI 教练报告(点击「AI 分析」生成)
5. 切到「AI 教练」直接对话(支持 minimax M3,带推理过程)
6. 「Dashboard」看整体训练负荷
7. 「个人画像」调整你的 FTP / 最大心率

## 架构

```
┌──────────────────────────────────────────────────────┐
│         React 前端 (Vite :1420)                      │
│   Dashboard · 训练 · 训练详情 · AI教练 · 导入 · 画像│
│   苹果毛玻璃风格 · 实时图表 · SSE 流式对话            │
└────────────────────┬─────────────────────────────────┘
                     │ HTTP (Vite 代理)
                     ▼
┌──────────────────────────────────────────────────────┐
│        Python Sidecar (FastAPI :8765)                │
│   FIT 解析 → 指标计算 → 个体画像 → AI 教练 Agent    │
│   SSE 流式 chat · Mock 数据生成器                    │
└────────────────────┬─────────────────────────────────┘
                     │ HTTPS
                     ▼
              minimax M3 / OpenAI 兼容 LLM
            (Mock 模式无需 key,本地直接跑)
```

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | React 18 + Vite 5 + TypeScript + Tailwind 3 + Recharts + Zustand + react-markdown |
| 后端 | Python 3.11+ + FastAPI + uvicorn |
| 数据 | SQLite + SQLAlchemy 2.0 |
| FIT 解析 | fitparse |
| 指标 | NumPy / SciPy / Pandas |
| LLM | minimax M3 / OpenAI 兼容协议 / Mock 兜底 |

## 目录结构(V0.2)

```
cycling-coach/
├── tools/                                # 工具脚本 (start/stop/diagnose/uninstall + .bat/.sh)
│   ├── start.bat / start.sh                # dev 模式启动
│   ├── stop.bat / stop.sh                  # dev 模式停止
│   ├── diagnose.bat / diagnose.py          # 诊断环境
│   ├── uninstall.bat / uninstall.sh        # 一键卸载 (含 --purge-data)
│   ├── build-windows-installer.bat         # 打 Windows NSIS Setup.exe
│   └── start.py / stop.py / diagnose.py    # Python 底层
├── .env.example                            # 配置模板
├── pyproject.toml                          # 根项目配置(monorepo 单包)
├── requirements.txt                        # 兼容老用户
│
├── cycling_coach/                          # 🆕 Python 命名空间根
│   ├── core/                                # 业务核心
│   │   ├── domain/                          #   实体 + 值对象
│   │   ├── services/                        #   业务服务
│   │   ├── profile/                         #   运动员画像
│   │   └── metrics/                         #   算法(NP/IF/TSS/zones/curves)
│   ├── data/                                # 数据访问
│   │   ├── parsers/                         #   FIT 解析
│   │   ├── sqlite/                          #   SQLite ORM
│   │   └── repositories/                    #   (V0.3+ 抽象层)
│   ├── ai/                                  # AI 层
│   │   ├── providers/                       #   LLM 客户端(m3 + fallback)
│   │   ├── prompts/                         #   prompt 模板
│   │   ├── tools/                           #   Agent tools
│   │   └── orchestrator/                    #   (V0.3+ 多轮)
│   ├── api/                                 # HTTP API
│   │   ├── main.py                          #   FastAPI 入口
│   │   ├── routers/                         #   6 个 REST 端点
│   │   └── streaming/                       #   (V0.3+ SSE 抽象)
│   ├── worker/                              # 🆕 后台任务(占位,V0.3+)
│   └── config/                              # 配置 + 日志
│
├── apps/                                   # 🆕 用户入口
│   ├── web/                                 # ✅ Web 前端(原 frontend/)
│   ├── desktop/                             # ✅ 桌面端 (Electron + electron-builder)
│   │   ├── main.cjs / preload.cjs / package.json
│   │   ├── build/                            #   图标 + PyInstaller spec
│   │   └── README.md
│   ├── mobile/                              # 🆕 移动端(PWA 占位)
│   └── cli/                                 # 🆕 CLI(占位,V0.3+)
│
├── tools/                                  # 🆕 工具脚本 (start/stop/diagnose/uninstall + .bat/.sh)
│   ├── start.bat / start.sh                # dev 模式启动
│   ├── stop.bat / stop.sh                  # dev 模式停止
│   ├── diagnose.bat / diagnose.py          # 诊断环境
│   ├── uninstall.bat / uninstall.sh        # 一键卸载 (含 --purge-data)
│   ├── build-windows-installer.bat         # 打 Windows NSIS Setup.exe
│   └── start.py / stop.py / diagnose.py    # Python 底层
│
├── tests/                                  # 🆕 跨层测试
│   ├── unit/                                # 单元测试
│   ├── integration/                         # 集成测试
│   └── e2e/                                 # 端到端测试
│
├── scripts/                                # 一次性脚本
│   └── screenshot.mjs                       # 截图工具
│
├── assets/screenshots/                      # README 截图
│
├── workspace/                              # 运行时数据(gitignore)
│   ├── input/  /  output/
│   └── .gitkeep
│
└── docs/
    ├── ARCHITECTURE.md                     # 🆕 完整架构
    ├── ROADMAP.md                          # 🆕 路线图
    └── PLAN.md                             # 项目规划
```

**完整架构说明**:见 `docs/ARCHITECTURE.md`

## 数据模型

```sql
athletes     -- 运动员(单用户 MVP)
  id, name, ftp, ftp_estimated, max_hr, lthr, weight_kg, height_cm

activities   -- 训练记录
  id, athlete_id, source, start_time, duration_s, distance_m,
  avg_power, max_power, avg_hr, max_hr, avg_cadence,
  metrics (JSON: NP/IF/TSS/EF/VI/MMP/HR_zones/...),
  samples_json (1Hz 1 小时内的样本),
  laps_json, report, report_status

workouts     -- AI 生成的训练课程(V0.2+)
preferences  -- KV 偏好
```

## Mock 模式

不配 `M3_API_KEY` 时,**所有 AI 调用自动走 mock 兜底**,返回一个基于真实指标的"假但合理"报告。

要在生产环境用真实 AI,在 `.env` 填入:
```ini
M3_API_KEY=sk-or-v1-...
M3_BASE_URL=https://openrouter.ai/api/v1
M3_MODEL=minimax/minimax-m3
```



## 卸载

### 桌面端 (装了 Setup.exe)

3 种方式:
1. **开始菜单** → `Cycling Coach` 文件夹 → 卸载快捷方式
2. **Windows 设置** → 应用 → 安装的应用 → `Cycling Coach` → 卸载
3. **控制面板** → 程序与功能 → `Cycling Coach` → 右键卸载

NSIS uninstaller 默认 **保留用户数据** (`%APPDATA%\CyclingCoach\`),
卸载时弹 "同时删除数据?" 选是才彻底清.
训练历史 (活动/计划/PMC) 在 SQLite, 删了不可恢复.

### Dev 模式 (没装过 Setup.exe)

`tools\uninstall.bat` (Windows) / `./tools/uninstall.sh` (Unix):
- 默认: 清 build artifacts, 保留用户数据 + .venv
- `--purge-data`: 全清 (含 workspace 用户数据)
- `--keep-venv`: 保留 .venv (快速重建用)

不动 `kb_source\` (训练百科源) / 源码 / `.env` 等配置.

## 桌面端打包

```bat
:: Windows 用户
tools\build-windows-installer.bat
```

产物: `apps\desktop\dist-electron\CyclingCoach-Setup-0.5.3-x64.exe` (~250 MB).
详见 [docs/DESKTOP-BUILD.md](docs/DESKTOP-BUILD.md).

## 常见问题

### 启动后访问 127.0.0.1:1420 白屏

检查启动 cmd 有没有报错:
- 后端是否 `Application startup complete`
- 前端是否 `Local: http://127.0.0.1:1420/`

### 上传 FIT 失败

V0.1.0 只支持 `.fit` 文件,其他格式(`.tcx` / `.csv`)留 V1.0。

### 端口 8765 / 1420 被占用

Windows:
```cmd
netstat -ano | findstr :8765
taskkill /F /PID <pid>
```
macOS / Linux:
```bash
lsof -i :8765
kill -9 <pid>
```

或者直接 `tools\stop.bat` / `./tools/stop.sh` 清理。

## 截图

| Dashboard | 训练详情 |
|---|---|
| ![](assets/screenshots/L01-dashboard.png) | ![](assets/screenshots/V04-detail-full.png) |
| **功率 / 心率区间** | **AI 教练** |
| ![](assets/screenshots/V02-zones.png) | ![](assets/screenshots/V03-ai-report.png) |
| **对话流式输出** | |
| ![](assets/screenshots/L05-chat-done.png) | |

## 关于知识库内容来源 — 潘震(公路车教练)

V0.5 训练百科与配套参考资料,内容来源是**潘震**(公路车教练)的授权转载。

### 潘震(公路车教练)

中国公路自行车领域的资深教练,长期从事青少年与业余车手的系统化训练指导工作。潘震教练将十余年一线执教经验系统整理为训练百科,覆盖训练方法、生理科学、训练执行、装备工具、青少年训练、执教知识等完整体系,内容涵盖功率训练、心率训练、室内骑行、力量核心、营养恢复、训练规划、训练误区、装备使用、骑行软件等公路车训练的全部核心环节。

V0.5 知识库是潘震教练授权将其训练百科内容以本地数据库形式整合进 Cycling Coach,让 AI 教练能够基于这些专业训练学知识回答用户问题、提供个性化训练建议。本项目仅做格式整理、入库与本地 RAG 检索,**不做任何内容增删或改写**。如需转载复用,仍请直接联系潘震教练本人。

## 致谢

- **训练百科与配套资料:潘震(公路车教练)** — V0.5 知识库 / RAG 全部内容来源
- 数据格式:Garmin FIT SDK

## License / 许可证

本项目采用**双协议 (Dual License)** 模式,代码与内容分开授权:

This project uses a **dual license** model — code and content are licensed separately:

### 📘 Software Code (软件代码)
- **License**: MIT
- **Files**: All source code under `cycling_coach/`, `apps/`, `tools/`, `docs/`, `README.md`
- **Copyright**: (c) 2026 lixvanran
- **Permitted**: ✅ Use · Copy · Modify · Distribute · Sublicense · Sell
- **Required**: 📋 Include copyright notice + LICENSE in all copies

**Full text**: [LICENSE](LICENSE) (English) | [LICENSE.zh-CN](LICENSE.zh-CN) (中文)

### 📕 Knowledge Base (知识库 `kb_source/`)
- **License**: Restricted Use (受限使用) — see [kb_source/LICENSE](kb_source/LICENSE)
- **Author**: **潘震(公路车教练)** (Pan Zhen, Road Cycling Coach)
- **Content**: 训练百科 (Training Encyclopedia) — 训练方法·车下训练·生理学·工具·常见问题
- **Permitted**: ✅ Local RAG retrieval · Backup with attribution
- **Prohibited**: 🚫 Redistribution · Modification for redistribution · Commercial use · Misattribution
- **Required**: 📋 Attribution "训练百科内容来源: 潘震(公路车教练)"

**Full text**: [kb_source/LICENSE](kb_source/LICENSE) (bilingual 中英双语)

### Why dual? (为什么要双协议?)
- The code is generic training-app infrastructure (MIT = maximally open for collaboration)
- 训练百科 (Training Encyclopedia) is 10+ years of original coaching content by 潘震(公路车教练)
  → deserves authorship protection, separate from the code that uses it
- 软件代码是通用的训练 App 基础设施 (MIT = 最大程度开放协作)
- 训练百科是潘震(公路车教练)十余年原创教练内容 → 值得独立保护

### Quick attribution in your fork (在你 fork 时署名)
```markdown
本项目基于 [cycling-coach](https://github.com/lixvanran/cycling-coach) (MIT License)
训练百科内容来源: 潘震(公路车教练) (Restricted Use)
```
