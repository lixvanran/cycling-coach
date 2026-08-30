# cycling_coach.worker

> 状态:**占位** — V0.3+ 启动

## 用例

- 后台批量分析(上传 N 个 FIT 串行处理)
- 同步推送(每周自动给用户发训练总结)
- 长期追踪(每周拉取 TSS / CTL / ATL)
- 通知(训练计划 / 恢复预警)

## 与 api 的关系

```
client ─── HTTP ──→ cycling_coach.api  (FastAPI)
                       │
                       │ enqueue
                       ↓
                  Redis/Queue
                       │
                       │ dequeue
                       ↓
                  cycling_coach.worker  (Celery / RQ / 自写)
```

V0.3 之前,简单的同步处理足够。
V0.3+ 引入 worker(推荐 Celery + Redis)。
