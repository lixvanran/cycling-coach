"""时间工具 —— 统一"UTC"和"本地日历日"两套语义 (V0.9.1 收口)

## 这里有个历史包袱, 值得说清楚

V0.8.3.1 加过一个 `utcnow_naive()`, 当时的假设是
"SQLAlchemy 的 DateTime 默认存 UTC naive"。这个假设**只对了一半**:

- `TrainingPhase.start_date / end_date` —— 用户填的日历日, 本地语义
- `Activity.start_time` —— 导入时显式 `replace(tzinfo=None)` 剥掉了 tzinfo,
  而 FIT 的 timestamp 解析成本地时间再剥掉。**存的是本地时间, 不是 UTC。**

也就是说: `utcnow_naive()` 和 `Activity.start_time` **从来就不在同一个
语义域里**, 只是两边都"看起来是 naive datetime", 比较不会报错,
于是错得极其隐蔽 —— 东八区每天有 8 小时的时间窗算错。

V0.9.0-07 逐处手修了一批(带 `🔴 V0.9.0-07` 注释), 但漏了一大片。
V0.9.1 把语义收口到下面几个函数:

- `local_now()`   - 和 `Activity.start_time` 比, 算"最近 N 天"
- `local_today()` - 和日期字段比, 分日历日 / 算周边界
- `utcnow_naive()` - **只有**真的要处理 UTC 瞬间时才用(跨时区同步、
  和外部 UTC API 对账), 拿去和 `Activity.start_time` 比就是错的

## 新代码默认用 local_*

拿不准就问: "我比对的这个字段, 是用户填的日历日, 还是从设备解析来的?"
- 用户填的 -> `local_today()`
- 设备来的(已剥 tzinfo) -> `local_now()`
- 确实是 UTC -> 才用 `utcnow_naive()`
"""
from __future__ import annotations

from datetime import date, datetime, timezone


def local_now() -> datetime:
    """当前本地时间 (naive)。

    和 `Activity.start_time`(入库时已剥掉 tzinfo, 且语义就是本地时间)
    在同一个语义域里, 可以直接比较。

    ⚠️ 不要用 `datetime.utcnow()` 代替 —— UTC+8 下整整偏 8 小时,
    每天早上有 8 小时的窗口归错日期。
    """
    return datetime.now()


def local_today() -> date:
    """当前本地日历日。分天 / 按天比较时用这个。"""
    return date.today()


def utcnow_naive() -> datetime:
    """当前 UTC 时间 (naive) —— 替代 deprecated `datetime.utcnow()`。

    等价于 `datetime.now(timezone.utc).replace(tzinfo=None)`。

    ⚠️ **只在真的是 UTC 语义时用**。拿去和 `Activity.start_time`
    或 `TrainingPhase.*_date` 比较会偏整个时区差 —— 那些字段是本地语义。
    绝大多数业务场景应该用 `local_now()` / `local_today()`。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)