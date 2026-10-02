# Cycling Coach 工程调研报告 V0.8.1 → V0.8.2/V0.9/V1.0

> **目的**:在三阶段工程化路线图开干前, 摸清 V0.8.1 的真实状态, 校准每阶段任务清单。
> **范围**:Clone 到本地、读代码、读 CHANGELOG、读 ROADMAP、读 PERFORMANCE_AUDIT、对比 README 数字。
> **未跑测试**:沙箱 Debian 11 PEP 668 + 装到一半 zombie, 环境装不上; 真实测试在 stage 1 第一个 CI 任务里跑。
> **位置**:`/workspace/cycling-coach/`, 不推 GitHub, 等你 review。

---

## 0. 仓库现状 (V0.8.1)

| 维度 | 数据 |
|---|---|
| 仓库大小 (排除 .git + kb_source) | **7.2 MB** |
| 文件数 (排除 .git + kb_source) | **275 个** |
| 后端代码 (`cycling_coach/`) | ~**5000+ 行** (service 2682 + router 4973 + ai + config + core) |
| 前端代码 (`apps/web/`) | 17 pages + 5 layouts + 5 common + store/hooks/lib/components |
| 测试文件 | **5 个** (`test_chat_persistence_v076.py` 293 行 / `test_ftp_predictor_v080.py` 428 / `test_idor_v081.py` 194 / `test_services_v080.py` 504 / `test_workflow_v080.py` 543) |
| 测试类 (Test*) | **25 个** |
| test\_\* 方法 (含类内) | **72 个** (无 parametrize 展开) |
| Python 服务路由 | **27 个** router 文件 (不是 README 说的 22) |
| ORM 表 | **16 张** |
| Pydantic v2 模型 | **51 个** BaseModel |
| Frontend 测试 | **1 个** (`ChatPage.test.tsx`) |
| Stars/Forks/Watchers/Issues | **0/0/0/0** |

---

## 1. README 数字 vs 实际 (重要)

| README 声称 | 实际看到 | 差距 |
|---|---|---|
| 137 + 2 skip 测试通过 | 25 个 Test* 类, 72 个 test\_\* 方法 | **少了 65+** —— README 数字虚标或与历史口径不一致 |
| 22 模块 / 107 paths / 126 methods | 27 个 router 文件 | **多了 5 个** (chat / ml / frontend / dev / diagnose) |
| 21 模块 | 27 | **多了 6 个** |
| Strava 同步 V0.7.8+ 实际联通 | `routers/sync.py:34` 写 "V0.7.4 状态: 接口预留, 暂不实现 OAuth" | **完全没联通** |
| .github/ CI 已就绪 | **`.github/workflows/` 不存在**, 只有 FUNDING + Issue 模板 + PR 模板 | **CI 0** |
| 23 个 commits ahead of V0.8.0 | 仓库干净, 无未提交 | (n/a) |

**结论**:V0.8.1 CHANGELOG 是真实记录, 但 README 顶部的"卖点数字"是写代码时的快照, 没跟 CHANGELOG 同步。**这是 stage 1 第一个低垂果实**:把 README 数字跟代码同步。

---

## 2. 阶段 1 任务现状对照 (8 个任务)

| 任务 | 现状 | 缺口 | 优先级 |
|---|---|---|---|
| **1.1 测试覆盖 + 真数字** | pytest 已配, 25 个 Test* 类, 72 个 test\_\* 方法 | 没装 pytest-cov, 不知道覆盖率; 没装 pytest-benchmark 跑回归; 测试 fixture 散落不一致 | **P0** |
| **1.2 CI 真落地** | `.github/workflows/` **不存在**; ruff/mypy 已在 dev deps; tests/ 已有 | 没有 Actions 配, 没有 coverage 上报, 没有前端 build 任务, 没有 PR 强制检查 | **P0** |
| **1.3 结构化日志 (JSON)** | `config/logging.py` 30 行, 格式是 `%(asctime)s \| %(levelname) \| %(name) \| %(message)s` | 没 request_id, 没 stage, 没 duration_ms, 没 athlete_id; 不能被 Loki/ELK 直接吃 | **P1** |
| **1.4 统一异常** | ✅ `core/exceptions.py` 100+ 行, AppError + 5 子类 (NotFound/Validation/Conflict/Forbidden/Unauthorized) + BusinessError; `api/main.py` 已注册 handler; service 层用得很整齐 | 仅一个细节: router 还能看到 `raise HTTPException(...)` 散落, 需扫一遍替换 | **P2** |
| **1.5 健康检查** | `routers/diagnose.py` 有 `/api/diagnose` + `/api/health` | 没拆 /live /ready /startup (K8s 标准三件套); /health 不检 DB | **P2** |
| **1.6 配置管理** | ✅ `pydantic-settings` BaseSettings 已经在 `config/config.py` 95 行用了; 5+ 模块化字段 (LLM/后端/前端/CORS/workspace/desktop/kb/ml/multi-mind) | `.env.example` 51 行太简, 缺文档; 缺启动时校验 (缺 m3_api_key 是否走 mock 走提示) | **P2** |
| **1.7 安全复审** | ✅ IDOR 防护 (V0.8.1 批 2, 4 service × 15 方法); ✅ python-multipart CVE 升 0.0.31; ✅ 50MB 上传大小限制; ✅ 路径遍历防护 (safe_basename); ✅ CORS 配白名单; ✅ SQL 白名单 (_ALLOWED_TABLES) | XSS sanitize 用了 rehype-sanitize 但要确认覆盖; 速率限制**没有**; 敏感信息 (API key) 启动日志没脱敏 | **P1** |
| **1.8 性能基准** | ✅ SQLite WAL + busy_timeout=5000 (V0.7.8); ✅ samples_json defer; ✅ 索引补齐 (tss / np / act_athlete_start / daily_metrics); ✅ trends SQL 聚合; ✅ Vite manualChunks (V0.8.0); ✅ 17 页面 lazy | 没 pytest-benchmark 留基线; SSE 长连接占 worker 没说怎么量化; 旧 886KB chunk 问题 PERF_AUDIT 提了但没量化现在大小 | **P1** |

**调整后优先级**:
- **P0 (必做, 阶段 1 前 2 周)** : 1.2 CI + 1.1 测试覆盖 + README 数字同步
- **P1 (必做, 阶段 1 第 2-3 周)**: 1.3 结构化日志 + 1.7 安全复审 (速率限制+key 脱敏) + 1.8 性能基线
- **P2 (可推到阶段 1 末)**: 1.4 统一异常 (扫尾) + 1.5 健康检查 /live/ready/startup + 1.6 配置文档

---

## 3. 阶段 2 / 3 任务前置条件评估

### 阶段 2 关键依赖
| 任务 | 前置 |
|---|---|
| **Alembic 迁移** | 16 张表现状是 SQLAlchemy 2.0 DeclarativeBase + `_auto_migrate` (跑列 ADD COLUMN, 不建索引); 需要 baseline 迁移 + 后续 DDL 走 migration | **V0.9.0 必做** |
| **多用户 + JWT 认证** | 当前 `services/*.py` 全在 `__init__` 里 `self.athlete = profile_store.get_or_create_athlete(db)` — 单用户假设; 多用户需要拆出 `user_id` → `athlete_id` 的 1:N 关系; `get_services` 注入从单 athlete 改成"current user → 找默认 athlete" | **V0.9.0 大头** |
| **异步任务 (Arq/dramatiq)** | `worker/` 目录是**空架子** (只有 README + 空 `__init__.py`); `services/tasks.py:run_analyze_task` 是同步函数, 通过 FastAPI `BackgroundTasks` 跑 (PERF_AUDIT 已警告); V0.8.0 README 说"计划换 Arq" 但没动 | **V0.9.0 必做** |
| **缓存层** | 4 块缓存 (KB 检索 / AI 回复 / ML 推理 / 指标计算) — 当前全无 | V0.9.0 |
| **ML 推理监控** | `ml/registry.py` 已实现 Conformal 区间 + ModelHandle; 但 metrics 暴露 (Prometheus) 还没有 | V0.9.0 |
| **数据导入优化** | 解析是同步 `await asyncio.to_thread(FitParser().parse_file)`, 大文件没流式; 导入进度没暴露; 失败回滚靠 `db.rollback()` 但 activity upload 流程里没 try/except 包 | V0.9.0 |

### 阶段 3 关键依赖
| 任务 | 备注 |
|---|---|
| **容器化** | `requirements.txt` 严重过期 (见 §4), 装 Docker 前必须先修; 没 Dockerfile, 没 docker-compose |
| **可观测性** | Prometheus metrics 还没暴露; 错误上报 (Sentry) 还没接 |
| **可靠性** | 没 DB 备份/恢复工具; 优雅降级 (LLM 走 Mock) 已有但 KB/ML 降级没说清楚 |
| **PWA + 移动端响应式** | 前端没 PWA manifest; 移动端响应式现状未知 (没设备测过) |
| **i18n** | 前端没 i18n 框架 (i18next / react-intl 都没装) |
| **API SDK 生成** | OpenAPI 自动出; 没装 openapi-generator |
| **数据导入导出** | 有 exporters (zwo/mrc/erg/fit/json), 但**全量数据导出** (含 KB 元数据/chat 历史/AI 报告) 没有 |

---

## 4. 现有工程债 (无关阶段, 但要修)

### 4.1 `requirements.txt` 严重过期 (P0)
- **多了**: `aiofiles`, `scipy` (V0.8.1 删了, 没同步)
- **少了**: `joblib`, `onnxruntime` (V0.7.6 加了, requirements.txt 没加), `ruff`, `mypy` (dev deps, 没加)
- **重复**: `reportlab` 重复 1 次, `fit-tool` 重复 1 次
- **没装 dev 依赖**: ruff/mypy 在 pyproject.toml `[project.optional-dependencies].dev`, 但 requirements.txt 没分块
- **建议**: 直接删 `requirements.txt`, README 改一句 "用 `pip install -e .[dev]` 装". pyproject.toml 才是 SSOT.

### 4.2 README 数字与代码不同步 (P0)
- 测试数: README 137+2 skip, 实际 25 类/72 方法
- 端点数: README 21/22, 实际 27 router
- Strava 同步: README V0.7.8+ 联通, 实际未实现
- CI: README V0.8.1 批 3 已配, 实际 `.github/workflows/` 不存在

### 4.3 CHANGELOG 与代码有脱节
- V0.7.5.3 声称 "补 ix_activities_tss 索引", 实测 (PERF_AUDIT V0.7.5.10) 用户库**没有**这索引, `_auto_migrate` 只 ADD COLUMN 不建索引 — V0.7.8 修了
- 这意味着 **README/CHANGELOG 写的不一定真做了**, 需要每条都用代码验证

### 4.4 `data/sqlite/database.py:_ALLOWED_TABLES` (中等)
- 白名单里**没有** `daily_metrics`, `preferences`, `kb_*` 等表
- V0.7.5.4 DEV-19 限制了 `_auto_migrate` / `repair_db` 操作范围
- 但新增表忘了加白名单会**静默失败** (PermissionError 但被 except 吞)

### 4.5 前端缺测试基础 (P1)
- `apps/web/src/__tests__/` 只有 `ChatPage.test.tsx` 1 个
- package.json 里有 `puppeteer-core` (25MB+), 但 vitest/jest config 没看到
- 前端 17 页面 0 单元测试, 靠 manual

### 4.6 文档分散 (P2)
- `INSTALL_V0.7.8.md`, `INSTALL_V0.8.0.md`, `INSTALL_V0.8.1.md` 三个文件, 高度重复
- `PERFORMANCE_AUDIT_V0.7.5.10.md` 重要文档, 但没进 `docs/`
- `V0.7.8_REPORT.md`, `V0.8.0_REPORT.md` 也散落根目录
- 建议: 历史报告归档到 `docs/history/`, INSTALL 留一个最新版 + CHANGELOG 链接

---

## 5. 阶段 1 推荐任务清单 (按"价值/工时"排序)

> 工时是单人估算; 不含 review + 测试 + 反馈循环。

### Batch A — 基础设施 (P0, 3-5 天)

#### A1. 修 `requirements.txt` 或删了
- **现状**: 文件 33 行, 跟 pyproject 严重不一致
- **改动**: 直接删文件, README 改 "用 `pip install -e .[dev]` 装"
- **风险**: 0 (项目当前主用 pyproject.toml, requirements.txt 估计没人看)
- **工时**: 0.5h

#### A2. 装本地 dev 环境 + 跑通测试
- **现状**: 我在沙箱没装上, 你本地 Mac/Win 跑一次
- **任务**: `python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
- **命令**: `pytest -v --tb=short` 收集 25 类 / 72 方法
- **真数字**: 实际通过/失败/跳过的真实数
- **工时**: 1-2h (含装包时间)
- **风险**: 1-2 个测试可能因 import 路径或 fixture 不稳失败, 记下来修

#### A3. 加 `pytest-cov` + `pytest-benchmark` + 第一次覆盖率报告
- **改动**: `pyproject.toml` `[project.optional-dependencies].dev` 加 `pytest-cov`, `pytest-benchmark`; `pyproject.toml` `[tool.pytest.ini_options]` 加 `--cov=cycling_coach --cov-report=term-missing --cov-report=xml:coverage.xml --benchmark-disable`
- **真数字**: 第一次 baseline 覆盖率, 按模块分 (core/metrics, core/services, core/ml, ai/, api/routers)
- **建议**: 在 `tests/` 加一个 `conftest.py` 放共享 fixture
- **工时**: 2h (装包 + 跑 + 读报告)
- **风险**: 可能有循环 import 触发 coverage 路径 bug, 必要时加 `# pragma: no cover` 标记

#### A4. 建 `.github/workflows/ci.yml` (前后端一锅端)
- **现状**: `.github/workflows/` 不存在
- **改动**:
  - `ci.yml`: Python 3.11 + `pip install -e .[dev]` + `ruff check .` + `ruff format --check .` + `mypy cycling_coach/` + `pytest --cov=cycling_coach --cov-fail-under=60 --cov-report=xml` + Node 20 + `pnpm install` + `pnpm build` (apps/web)
  - 加 coverage 上报到 Codecov (需 Codecov token, 用 `secrets.CODECOV_TOKEN`)
  - PR 触发; main 触发; 失败阻止 merge
- **风险**: V0.8.1 README 说"待 token workflow scope 后入仓" — 你 GitHub token **没 workflows scope**; 需要去 https://github.com/settings/tokens 加 `workflow` scope 重新生成
- **工时**: 3-4h (写 yml + 调试到绿)
- **验收**: PR 触发 CI, lint/typecheck/test/build 全绿, 覆盖率报告显示

#### A5. 修 README 数字 (test 数 / 端点数 / 同步状态)
- **现状**: README 多个数字与代码不一致
- **改动**:
  - 顶部 badge: `tests-passing` 数字
  - "端点概览" 表格: 21 → 27 (含 chat / ml / frontend / dev / diagnose 5 个)
  - 删 "Strava V0.7.8+ 联通" 改 "Strava 框架就绪, OAuth V0.9 实装"
  - "GitHub Actions CI" 段: 从"待 token workflow scope" 改成已完成
- **工时**: 1h
- **风险**: 0

### Batch A 总工时: ~2-3 个工作日

### Batch B — 质量与可观测性 (P1, 5-7 天)

#### B1. 结构化 JSON 日志
- **现状**: `config/logging.py` 普通 logging format
- **改动**:
  - 加 `python-json-logger` 到 deps
  - 写一个 `JsonFormatter` (或直接用 python-json-logger)
  - 字段: timestamp, level, logger, message, request_id (contextvar), stage, duration_ms, athlete_id, session_id
  - 加 `request_id` middleware (生成/继承 `X-Request-ID` header)
  - 关键路径 (router 入口, service 方法, LLM 调用) 用 `logger.info(..., extra={"stage": ...})`
  - 保留人类可读格式作为开发模式 (settings.is_dev)
- **工时**: 6-8h
- **验收**: 跑 `curl http://localhost:8765/api/health` 看响应 + 日志一行 JSON; 同时多请求并发能区分

#### B2. 速率限制
- **改动**: `slowapi` 加到 deps, 在 FastAPI app 装 limiter; 限 /api/*/upload (10/min), /api/coach (20/min), /api/ml/predict (30/min), /api/chat/* (60/min)
- **工时**: 3-4h
- **验收**: 高频请求返回 429; 不同端点独立限流

#### B3. 敏感信息脱敏
- **现状**: 启动日志可能打印 m3_api_key / strava_client_secret
- **改动**: 自定义 `logging.Filter` 把 `key=`, `password=`, `secret=`, `token=` 后面的值替换成 `***`; 跑一次启动确认
- **工时**: 2h
- **风险**: 0

#### B4. 性能基线 (pytest-benchmark)
- **改动**: 选 3-5 个热路径 (FIT 解析 1h, ActivityDetail 加载, trends.volume, ml.predict.ftp, KB search), 写 `tests/benchmarks/test_bench_*.py`
- **验收**: pytest-benchmark 留 JSON 基线; CI 不 fail (只警告回归 > 20%)
- **工时**: 4h
- **风险**: 0

#### B5. 文档归档
- **改动**:
  - `docs/history/V0.7.5.10_perf_audit.md` ← `PERFORMANCE_AUDIT_V0.7.5.10.md`
  - `docs/history/V0.7.8_report.md` ← `V0.7.8_REPORT.md`
  - `docs/history/V0.8.0_report.md` ← `V0.8.0_REPORT.md`
  - `docs/INSTALL.md` ← 留 `INSTALL_V0.8.1.md`, 其它两个加 redirect
  - README "文档" 段更新链接
- **工时**: 1h
- **风险**: 0

### Batch B 总工时: ~4-5 个工作日

### Batch C — 收口 (P2, 3-4 天)

#### C1. 异常统一扫尾
- 任务: `grep -r "raise HTTPException" cycling_coach/api/routers/` 全替换
- 工时: 2-3h
- 验收: 业务异常全部走 AppError → handler

#### C2. 健康检查 /live /ready /startup
- 任务: `routers/diagnose.py` 加 3 个端点, /ready 检 DB + KB 状态
- 工时: 2-3h
- 验收: K8s/容器直接探针可用

#### C3. 启动校验 + 友好 mock 提示
- 任务: `config/config.py` 加 `model_validator`, 缺关键配置启动时给明确报错
- 工时: 2h
- 验收: 没 m3_api_key 启动时提示 "Mock 模式已开启, 不消耗 LLM 额度", 有 key 但错时提示 "Key 看起来有问题, 走 Mock 兜底"

#### C4. CHANGELOG V0.8.2 段
- 写一份 Batch A+B+C 收口的变更日志
- 工时: 1h

### Batch C 总工时: ~2 个工作日

---

## 6. 阶段 1 总工时 + 节奏建议

- **Batch A** (3-5 天): 全部 P0
- **Batch B** (5-7 天): 全部 P1
- **Batch C** (3-4 天): 全部 P2
- **总**: 11-16 个工作日 (3 周单人)

**建议节奏**:
- 第 1 周: Batch A 全清 → 第一次 CI 绿 → README 数字真
- 第 2 周: Batch B 全清 → 日志 JSON + 限流 + 性能基线
- 第 3 周: Batch C 收口 → V0.8.2 tag 发布

**V0.8.2 命名建议**: "**质量与可观测性收口**" (对齐 V0.8.0 战术规划, V0.8.1 工程化收口)

---

## 7. 风险与建议

### 7.1 风险
1. **GitHub Actions 没 workflow scope**: 你 token 需要加 `workflow` scope 才能创建 `.github/workflows/`. **A4 任务前置**.
2. **前端 CI 装包慢**: pnpm install 第一次 1-3 分钟, CI 跑完 5-8 分钟. 接受.
3. **覆盖率从 0 起算会很惨**: `pytest --cov-fail-under=60` 第一次可能挂; 建议**先不加 fail-under**, 等 Batch B 末看真数字再决定目标.
4. **慢测试**: `test_workflow_v080.py` 543 行, 跑完可能 30s+; 不入 CI 主线, 拆 `tests/integration/` 跑 nightly.
5. **ruff 一次扫会一片红**: 项目历史代码可能没 ruff 过; CI 加 `ruff check . --fix` 自动修不了的留 warning 不 fail, 后续 PR 慢慢清.
6. **V0.8.1 报的数字"137+2 skip"**: 可能某个老 commit 时代确实是, 现在代码重构丢了几个测试. 别硬追这个数, 用"现在跑通 X 个, 历史峰值 137" 替代.

### 7.2 建议
- **先 Batch A 全过, 再开 Batch B**. CI 绿了再写新测试/新代码, 否则测了不算.
- **每个任务做完都 git commit**, 独立 PR, 你 review 一个过一个, 容易回滚.
- **Codecov / SonarCloud 慢一步**: 第一版 CI 不接外部服务, 等覆盖率真数字出来再决定.
- **V0.8.2 标签在 Batch A 末就能打** (CI 绿 + 数字真) — 不必等 Batch B+C. 阶段性胜利要早拿.

### 7.3 我不打算做的
- 改 service 层业务逻辑 (阶段 1 只做"质量", 不动功能)
- 改前端 UI / 业务 (阶段 1 也不动)
- 引入重型框架 (Django, Next.js, 等) — 项目已经定型
- 引入重量级可观测性栈 (OpenTelemetry, Datadog) — 阶段 3 才上, 阶段 1 用轻量自研

---

## 8. 下一步: 你拍板

按你的工作流 ("先规划、再执行、先给 zip 预览、用户同意后才推 GitHub"):

1. **现在**:
   - 这份报告在 `/workspace/cycling-coach/ENGINEERING_AUDIT_V0.8.1.md` ✅
   - 没动任何业务代码
   - 没推 GitHub
   - 调研用过的文件/数据都在 workspace 留底

2. **等你决定**:
   - **A**: 同意 Batch A 全做 → 我按 5 个子任务顺序做, 每个做完给你 diff 摘要 + 关键文件预览, 同意后才 commit
   - **B**: 只做 A1 + A2 + A4 (最小可工作 CI) → 2 天, 先把 CI 跑起来
   - **C**: 报告有地方要调整 → 你说哪条改哪条
   - **D**: 整个方案重做 → 你说方向

3. **不会发生**:
   - 不会推任何东西到 GitHub
   - 不会动业务逻辑
   - 不会跑 `git commit` / `git push`

你拍。
