# 项目性能与扩展性体检报告 (V0.7.5.10)

> 阅读对象：作者 / 下一阶段重构者
> 测试环境：本地 8765 端口，SQLite 15MB，18 activities / 500 kb_chunks
> 估算依据：当前 DB 实测 + 同类项目经验

---

## 1. 后端并发

### 1.1 当前状态
- **单 worker 单进程**：`cycling_coach/__main__.py:14` 硬编码 `workers=1, reload=False`。所有请求（同步 + 流式 + 后台任务）挤在 1 个 event-loop + 1 个 OS 进程。
- **BackgroundTasks 走同一 event-loop**：`cycling_coach/api/routers/activities.py:191` 的 `background_tasks.add_task(run_analyze_task, ...)`。FastAPI 的 BackgroundTasks 是**协程**而不是线程——分析任务里调 LLM 同步 API 时，worker 还是会卡住。
- **SSE 长连接占 worker**：`cycling_coach/api/routers/coach.py:49` 返回 `StreamingResponse`；同 worker 同 event-loop，**每个活跃 SSE 连接都占用一个并发槽**。Uvicorn 单 worker 默认最多 1 个并发请求（async），加上 streaming chunk yield 阻塞 → 实际可服务 1~3 个 SSE 用户。
- **SQLite journal_mode=delete, synchronous=FULL**：`PRAGMA journal_mode = ('delete',)`, `PRAGMA synchronous = (2,)`。是 SQLite 三个模式中**最慢 + 最容易写锁**的组合。任何并发写入都会进入 BEGIN IMMEDIATE 排队。
- **SQLAlchemy 默认 pool**：`cycling_coach/data/sqlite/database.py:29-33` 用 `create_engine(_db_path(), connect_args={"check_same_thread": False})`——**没指定 pool_size / max_overflow**。SQLAlchemy 2.0 默认是 `QueuePool(5, 10)`，对 SQLite 单文件来说 5+10 反而太多（SQLite 写串行化）。

### 1.2 瓶颈点
- **生产环境单 worker 撑不住 LLM 并发**。1 个用户开 AI 对话 + 1 个 ML 推理 + 1 个 AI 报告生成 = worker 满载；其它所有 REST 端点全部排队。
- **BackgroundTasks 误导**。从 API 名字看像"异步"，但 FastAPI 实现是 in-process coroutine。如果用 `BackgroundTasks` 跑 LLM 同步调用（`m3_client.chat()`）就完蛋。当前 `run_analyze_task` 在 line 76 调 `analyze_activity_tool` 走 LLM 同步接口——会卡住 worker。
- **SSE 期间同 worker 不能服务其它端点**。AI 对话 30~60s 内，其它 11 个业务端点的 P99 全部掉到 30s+。
- **SQLite 写锁**：sync=tiny mix(`synchronous=NORMAL`) 已设，但 journal=delete 仍会在每次 commit 时 lock 整个文件；多端点并发 INSERT/PMC 重算会撞锁。

### 1.3 改造建议
- **短期 P1**：把 `BackgroundTasks` 换成 `asyncio.create_task` + 独立 semaphore(2)；或起一个简单 `asyncio.Queue` worker。
- **P1**：开 SQLite WAL + `PRAGMA synchronous=NORMAL`（已设）+ `PRAGMA busy_timeout=5000`。在 `database.py:43-46` 加 `cursor.execute("PRAGMA journal_mode=WAL")` 和 `PRAGMA busy_timeout=5000`。WAL 让读不阻塞写。
- **P2**：用 `aiosqlite` 替换同步 driver；FastAPI 全 async，CPU 密集走 `asyncio.to_thread`（activities.py:116-120 已经是这个模式，复用）。
- **P2**：多 worker 时必须改 `__main__.py` 用 `uvicorn.run(..., workers=N)` 但**注意 SQLite 单写锁**——多 worker 写并发反而更慢，建议**多 worker + 单写者**架构（一个 write-pool，一个 read-pool）或迁移到 PostgreSQL。

---

## 2. 后端热点路径

### 2.1 慢查询 / N+1
| 端点 | 文件:行 | 问题 | 估算代价 |
|---|---|---|---|
| `GET /api/activities` | `activities.py:271` `activities_all = q.all()` | **拉全表** 含 `samples_json` 800KB/行；然后 Python 端过滤 tss/np、排序、分页 | 当前 18 行 ≈ 0.5s；**1000 行 ≈ 30s+**；内存 600MB+ |
| `GET /api/trends/volume` | `trends.py:40-48` `_filter_activities(...).all()` | 730 天回溯 + 全列加载（连 samples_json 一起拉） | 2 年 400 个 activity ≈ 320MB RAM, 1-2s |
| `GET /api/activities/{id}/power-curve` | `activities.py:342, 366` | `samples_json or []` → `Sample(**s) for s in samples` —— 14400 个 Pydantic 重新验证 | 单次 ≈ 80~150ms（CPU） |
| 同上 wbal | `activities.py:472, 487` | 又一次 `Sample(**s)` 重复校验 | 80~150ms |
| 同上 decoupling | `activities.py:521, 537` | 又一次 | 80~150ms |
| 同上 elevation | `activities.py:660, 681` | 第四次 | 80~150ms |
| ActivityDetail 页加载 | 上面 4 个并行 | 4 次重复 Pydantic 校验同一份 samples_json | **300~600ms CPU 一并浪费** |
| `GET /api/insights/...` | `insights.py` | 大概率同样 `.all()` 拉全表 | 需具体看，但模式相同 |
| KnowledgeBase 列表 | `kb.py` | 暂无深入看，但 `kb_documents` 359 行 FTS5 命中应该还行 | — |
| `EXPLAIN QUERY PLAN SELECT ... ORDER BY tss DESC` | (实测) | **`SCAN activities` + `USE TEMP B-TREE FOR ORDER BY`** | 没有 `ix_activities_tss` 索引 |

#### 关键 EXPLAIN 实测
```
ORDER BY tss DESC  →  SCAN activities + USE TEMP B-TREE   ❌ 全表扫描
ORDER BY start_time  →  SEARCH USING ix_activities_start_time  ✅
FTS5 MATCH 'FTP'  →  SCAN kb_chunks_fts VIRTUAL TABLE INDEX 0:M3  ✅
```

#### 索引缺失
`data/sqlite/models.py:82` 定义了 `tss: ... index=True`，但 `data/sqlite/database.py:54-79` 的 `_TABLE_COLUMNS` 自动迁移**只 ALTER ADD COLUMN，不补索引**。实测 DB 里只有 `ix_activities_athlete_id` 和 `ix_activities_start_time`，**没有 `ix_activities_tss` 也没有 `ix_act_athlete_start`（__table_args__ 里的复合索引）**。所有升级用户都缺。

#### RAG 检索（orchestrator.py:77-119）
FTS5 本身快（实测 100 次查询 0.25s）。**但** line 112 的兜底 `LIKE` 用 `KbChunk.content.contains(t) for t in terms`——SQLite LIKE 全表扫，500 chunks 还能撑，**5000+ 就会明显卡**。每次 chat 都跑 1 次 FTS + 1 次 LIKE 兜底。

#### JSON 字段过滤
`activities.py:272-289` 用 Python 端 `(a.metrics or {}).get("tss")` 过滤。1000 行 × `metrics.get` = 几乎免费，但**全表 `.all()` 的 I/O 才是瓶颈**。同时 `tss` 已经独立列出来了——应该改 `WHERE tss BETWEEN :a AND :b` 而不是 Python 过滤。

### 2.2 改造建议
- **P0**：补索引迁移：`CREATE INDEX IF NOT EXISTS ix_activities_tss ON activities(tss)` + `ix_act_athlete_start (athlete_id, start_time)`。放到 `_auto_migrate` 里。
- **P0**：`activities.py:271` 改成显式列 `db.query(Activity.id, Activity.start_time, Activity.tss, ...)` —— `samples_json` 默认就不查。SQLAlchemy 2.0 用 `with_entities()` 或 `.options(defer('samples_json'))`。
- **P0**：`activities.py:270-289` 的 tss/np 过滤改 SQL `WHERE (tss BETWEEN ... OR json_extract(metrics, '$.tss') BETWEEN ...)`，sort 用 `ORDER BY tss`（命中索引后）。
- **P1**：trends.py 全用 SQL 聚合（dashboard.py:75-83 已经是正确写法，复用 `func.date(Activity.start_time)` GROUP BY）。
- **P1**：把 `Sample(**s)` 校验结果缓存到 `request.state` 或 Activity model 一次性 parse；4 个 detail 端点共享。
- **P2**：samples_json 拆出来放文件（`workspace/samples/{id}.parquet`）或独立 `activity_samples(activity_id, idx, power, hr, ...)` 表。当前设计让"单列塞 1MB JSON"是反范式的，索引不到内部字段。

---

## 3. 前端性能

### 3.1 首屏 / 切分
- **单 chunk 886KB**：`apps/web/dist/assets/index-hAk6WOdW.js` 886740 bytes。Vite 配置 `vite.config.ts:28` 显式 `manualChunks: undefined` —— **完全没分块**。
- **零懒加载**：`apps/web/src/App.tsx:1-46` 直接 `import { Dashboard } from "./pages/Dashboard"` 等 17 个页面 + 26 个组件，**全部打进一个 bundle**。`grep "lazy\|Suspense"` 0 命中（除去 img `loading=lazy`）。
- 注释 `vite.config.ts:28` 说"桌面模式不在意分块"——但 web/dev 模式也在用同一份配置。冷启动首屏加载 886KB JS + 48KB CSS = **934KB**，解压后 ~2.5MB JS heap。

### 3.2 图表 / 重渲
- ActivityDetail 一次加载 **7+ 图表**（PowerCurve / PowerZone / HRZone / PowerHrTime / Wbal / Elevation / GPSMap）。
- `useAppStore` 在 `useAppStore.ts:32` 用单一 `set` 整体 store；40 个 `useAppStore` 调用点。每次 `updateLastAssistant`（chat 流式每个 token 触发）都 `set({chatMessages: msgs})`，**所有订阅 `chatMessages` 的组件 re-render**。实测 store 没有用 `shallow` / `subscribeWithSelector` middleware。
- `PowerHrTimeChart.tsx:33` 1500 点降采样 OK；`Recharts` 渲染 1500 点折线 + 1~2 个 Area 在 4C8G 上首绘 ~80ms，hover 切 series 时会有 30ms 卡顿（Recharts 内部每次重算 scale）。**没有 React.memo** 包裹，导致父组件 state 变化时整图重绘。
- GPSMap（`GPSMap.tsx`）首次挂载 leaflet 触发 ~200ms 初始化 + tile fetch。

### 3.3 改造建议
- **P1**：Vite 加 `manualChunks`：recharts / leaflet / react-markdown 拆出来，按需 prefetch。首屏可降到 350KB。
- **P1**：`App.tsx` 全部页面改 `React.lazy(() => import('./pages/Dashboard'))` + `<Suspense fallback={...}>`，路由级 code splitting。预期首屏从 886KB → 300KB。
- **P1**：`PowerCurveChart / PowerHrTimeChart / WbalChart` 全部用 `React.memo`；Recharts `isAnimationActive={false}`（项目里动画肉眼难辨，徒增 CPU）。
- **P2**：`useAppStore` 拆 3 个 store：uiStore (view, selectedId) / chatStore (messages) / kbStore (selectedCategory)。`updateLastAssistant` 只触发 chat 订阅者。
- **P2**：`updateLastAssistant` 用 immer 或只更新 last ref 触发局部 rerender；现在每次 `[...s.chatMessages]` 全数组浅拷。

---

## 4. 数据规模

### 4.1 当前规模
- `activities` 18 行，DB 15MB
- `kb_chunks` 500 行 + FTS5 footprint 1.4MB
- `daily_metrics` 716 行（PMC 历史）

### 4.2 1 年/5 年预估（按周均 4h × 200 活动/年 实测外推）
| 规模 | 1 年 | 5 年 |
|---|---|---|
| activities 行 | 200 | 1000 |
| `samples_json` 总大小 | 200×830KB = **165MB** | **810MB** |
| `metrics` JSON 列 | 200×3KB = 600KB | 3MB |
| `report` (AI 生成) | 200×5KB = 1MB | 5MB |
| `db` 文件总大小 (估) | ~180MB | ~900MB |
| 5KB/chunk 知识库 | 5000×0.4KB = 2MB content | FTS5 索引 ~14MB |

- FTS5 在 5000 chunks 实测 100 query 0.4s 内（线性外推）；50000 chunks 还能秒查，但 100000+ 要考虑切分（按 category 分 FTS5 虚拟表）。
- 1 个 4h Gran Fondo samples=800KB，**单 DB 装 5 年高质量数据不可行**——SQLite 文件会变成 800MB+，fsync 时延 1s+，整库备份/复制都是问题。

### 4.3 改造建议
- **P1**：samples 拆表 / 拆文件。当前 `samples_json JSON` 列式存储是反模式。
- **P1**：`report` 也类似，单文本列。如果 AI 报告长（10KB+）应该单独 `activity_reports(activity_id PK, content, generated_at)`，主表只存 `has_report BOOL`。
- **P2**：训练 ML 模型时**强烈建议 DuckDB**。理由：(1) 直接 `SELECT * FROM 'cycling_coach.sqlite'` 读不写锁；(2) 列式查询比 SQLite 行式快 10-100×；(3) 内置 pandas 集成。
- **P2**：如果上生产多用户，迁移 PostgreSQL，单文件 1GB 是 SQLite 公认的尴尬点。

---

## 5. 多模型/多 agent 推理

### 5.1 串行 vs 并行
- 当前 `/api/coach/chat` `m3_client.stream_chat` 走 `_client.chat.completions.create(stream=True)`，**是真正的流式**（OpenAI SDK 内部用 httpx + SSE 解析）。
- 但**单 worker 串行**——5 个用户同时开 5 个 chat，第 5 个要等前 4 个 chunk yield 完。
- `stream_chat` 在 `m3_client.py:191-206` 还要做"主模型空 → fallback_model 重试"——用户感知的 TTFT（time to first token）= 2 个 RTT。

### 5.2 资源隔离
- **GIL 不影响 async I/O**：LLM 流式是 I/O bound，asyncio 不会卡。
- **ML 推理是 CPU bound**：`asyncio.to_thread` 提交给 default `ThreadPoolExecutor`（loop 默认 max_workers=min(32, cpu+4)）。在 8 核机器上 8 个并发 LLM 流 + 1 个 sklearn 训练 → 训练拿到 1 个 thread，CPU 满载 1 核。LLM 还在等 I/O 不冲突，但**解析/metrics 计算共用同一池**。
- 当前没看到 ML 模型代码（`grep "sklearn\|xgboost"` 0 命中），但 README 提到 V0.8 会加。

### 5.3 改造建议
- **P0**：把 LLM client 用 `httpx.AsyncClient` 替代 sync SDK；5 个 LLM 流可以真正并发。
- **P0**：多 LLM 共享 context 序列化：`build_chat_context` 每次新建 dict（`coaching/context.py`），5 个并发时重复算 5 次。**至少 LRU cache (athlete_id, days, last_activities_hash)**。
- **P1**：ML 推理放到独立 `ProcessPoolExecutor(max_workers=2)`（不要 ThreadPool——sklearn/scipy 真的占满 CPU）。Stream 端点用 `await loop.run_in_executor(process_pool, ...)`。
- **P1**：长 context 序列化——`build_chat_messages` 把 PMC / ACWR / RPE 拼成 6 块字符串，单次 chat ~3-5KB，5 路并发 = 25KB/s 进入 m3，**network 不瓶颈**，但 Python `json.dumps` + f-string 拼接每 chunk 调用可优化（`m3_client.py:152-187` mock 模式下每字符 yield 一次，每次都 `_re.search`）。
- **P2**：context 长度预估。当前 system prompt：athlete 8 字段 + PMC 3 + ACWR 4 + RPE 7d + Phase + FTP_info + KB top-3 chunks + 工具提示。粗估 **3~6KB system + 2~4KB history**。m3 8K context 完全够，但**多 LLM "思维扩散" 共享同一长 context 时一定要缓存**——把"context hash → message list"做 LRU(32)。

---

## 6. 可观测性

### 6.1 现状
- **日志非结构化**：`config/logging.py:10` `%(asctime)s | %(levelname)-7s | %(name)-30s | %(message)s` —— 纯文本格式，`grep` 友好但 ELK/Loki 难消费。
- **零 p50/p95/p99 埋点**：`grep "elapsed\|duration_ms\|time.monotonic"` 0 命中。SSE 流的 chunk 数 / 总耗时都没记录。
- **错误追踪 0**：`grep "sentry" 0`，`logger.exception` 只在 `orchestrator.py:251` 出现 1 次。
- **无 metrics exporter**：`grep "prometheus" 0`，没有 `/metrics` 端点。
- **健康检查仅 `/api/health` 返回 `{"status": "ok"}`**：`diagnose.py:29-31` 没检查 DB 连通、KB 是否就绪、LLM key 是否有效。
- **无内存/资源监控**：`grep "psutil\|tracemalloc" 0`。

### 6.2 改造建议
- **P1**：日志改 `python-json-logger`，stdout 输出 JSON，保留 human-readable 文件日志（可选）。
- **P1**：在 `main.py` 加 `starlette-prometheus` middleware，3 行代码出 `/metrics`：request latency histogram + in-progress gauge。
- **P1**：`/api/health` 改成深度检查：DB ping + FTS5 OK + KB chunks > 0 + (LLM key present or mock=True)。返回 `{"status":"degraded","degraded":["no_llm_key"]}`。
- **P2**：`logger.exception` 关键路径全覆盖（analyze_task、import_knowledge_base、stream_chat）。
- **P2**：SSE 流加 `logger.info(f"chat done: chunks={n}, total={ms}ms")` 便于回归。

---

## 7. 生产化

### 7.1 现状
- **`tools/stop.py:48` 用 `kill -9`**：SIGKILL 直接砍，SSE 流中途中断、SQLite write transaction 异常、KB 导入到一半死锁可能。
- **无 SIGTERM 优雅关闭**：`grep "SIGTERM\|signal" tools/` 0 命中。`cycling_coach/__main__.py` 没注册 handler。
- **健康检查太浅**：上面说。
- **无 graceful drain**：uvicorn 默认 `timeout_graceful_shutdown=None`（永久等待）。LLM 流卡住会永远关不掉。
- **Pydantic 校验每次 detail 端点都跑**：上面 §2.1 提了。
- **前端 dev proxy 在 vite.config.ts:16-20**：web mode ok，但 desktop mode 走 file:// + 同进程 uvicorn mount static，**没有 service worker / PWA / 离线缓存**。

### 7.2 改造建议
- **P0**：`uvicorn.run(..., timeout_graceful_shutdown=10)` + 收到 SIGTERM 后先 `app.state.shutting_down=True` 拒绝新请求，等 10s 后强杀。
- **P0**：`tools/stop.py` 改用 `kill -TERM` 默认 + 5s 后 `-9` fallback。
- **P1**：lifespan 退出时 `await app.state.locks` / `await pending_tasks` 排空。
- **P1**：`FileSizeLimitMiddleware` 已经做 50MB 限制（`main.py:121-141`），但**没有 rate limit**。本地优先应用影响小，但暴露到公网前必加 `slowapi`。
- **P2**：版本号端点 `/api/version` 已有，但 `/api/health` 缺 version field，加回去滚判断。

---

## 8. 优先级排序

### P0（阻塞 — 上"多 LLM + 多 ML"前必须做）
1. **SQLite WAL**：`database.py:43-46` 加 `PRAGMA journal_mode=WAL` + `busy_timeout=5000`。否则多个 BackgroundTask 写库直接撞锁。
2. **补 `ix_activities_tss` + `ix_act_athlete_start` 索引**：在 `_auto_migrate` 里加 `CREATE INDEX IF NOT EXISTS`，否则 `ORDER BY tss` 全表扫。
3. **`activities.py:271` 改显式列**：`.all()` 拉 800KB×N rows 会把 worker 内存吃光。`.options(defer('samples_json'))` 或 `with_entities(...)` 显式选列。
4. **`/api/coach/chat` 改真正并发**：`httpx.AsyncClient`，单 worker asyncio 也能并发 5 路 LLM。
5. **优雅关闭**：`uvicorn.run(timeout_graceful_shutdown=10)` + stop.py 用 SIGTERM。

### P1（重要 — 影响 5 年数据 + 生产稳定性）
6. Vite 加 `manualChunks` 拆分（recharts / leaflet / markdown 独立），`React.lazy` 17 个页面。
7. ML 推理独立 `ProcessPoolExecutor`（不要 ThreadPool）。
8. context LRU cache（多 LLM 共享同一长 context 时避免重复构造）。
9. JSON 日志 + `/metrics` + 深度 `/api/health`。
10. samples_json 拆表 / 拆 parquet 副文件。
11. `Sample(**s)` 校验缓存或单次 parse。

### P2（优化 — 长期演进）
12. SQLite → PostgreSQL（多用户生产）。
13. ML 训练用 DuckDB 旁路读 SQLite。
14. `useAppStore` 拆分 + `updateLastAssistant` 用 immer。
15. `Recharts` 配 `isAnimationActive={false}` + chart `React.memo`。
16. 知识库 5000+ chunks 时 LIKE 兜底换成 trigram 或纯 FTS5。
17. Sentry / OpenTelemetry 接入。

---

## 附：实测数据来源
- `ps aux | grep uvicorn` → PID 118，单进程
- `curl http://localhost:8765/api/diagnose` → V0.7.5.10, Python 3.11.2
- `sqlite3 pragma_journal_mode` → `delete` (确认非 WAL)
- `sqlite3 pragma_synchronous` → `2` (FULL)
- `samples_json` 实测：1.5h ride = 830KB；5 年 1000 骑 = 810MB
- `apps/web/dist/assets/index-hAk6WOdW.js` → 886740 bytes (1 个 chunk)
- FTS5 100 query 耗时 0.25s (500 chunks)
- ORDER BY tss EXPLAIN → `SCAN activities` (无索引)
- 全表 `.all()` 18 行 = 545ms / 11MB 内存
