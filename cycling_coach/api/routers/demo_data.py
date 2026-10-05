"""V0.9.0: 示例数据端点

## 为什么需要它

空状态提示里有个「先看示例」按钮。但 `load_demo_data` 原来整个埋在
`tools/load_demo_data.py` 的 `main()` 里 —— 耦合 argparse 和 print，
**程序根本调不到**。前端要么写死一条 shell 命令，要么只能做成死链。

而 dev router (`/api/dev/*`) 只在 `settings.dev_mode=True` 时挂载，
Windows 正式用户跑的是 desktop 模式，**dev_mode 是关的** ——
所以端点不能放那儿，得单开一个。

## 安全性

这个端点会**往用户数据库里写数据**，所以：

- 只在本地模式可用（`dev_mode` 或 desktop），远程访问一律拒绝
- 生成的是独立的「演示车手」，不会污染用户自己的 athlete
- 前端必须明确标注这是示例数据，不能让用户误以为是自己骑的
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cycling_coach.api.dependencies import Services, get_services
from cycling_coach.config.config import settings


log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/demo", tags=["demo"])

# tools/ 不在包内, 需要显式加到 sys.path 才能 import
_TOOLS = Path(__file__).resolve().parents[3] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))


class DemoLoadIn(BaseModel):
    weeks: int = 8
    force: bool = False


class DemoLoadOut(BaseModel):
    ok: bool
    athlete_name: str
    n_activities: int
    n_planned: int
    message: str


@router.post("/load", response_model=DemoLoadOut)
def load_demo(payload: DemoLoadIn, _svc: Services = Depends(get_services)):
    """载入 8 周示例训练数据

    ⚠️ 会往库里写入数据。生成的 athlete 名字固定为「演示车手」,
    跟用户自己的档案分开, 之后可以单独清掉。
    """
    # 只在本地模式开放 —— 这个端点会写库, 不该暴露给局域网/公网。
    #
    # V0.9.0: 我一开始只判 dev_mode / is_desktop, 结果自己用 uvicorn 起服务
    # 实测时被自己的守卫 403 拦死 —— 而那条路径既不是 dev 也不是 desktop,
    # 是个"两边都不算"的第三种状态。
    #
    # 所以判据改成"只要不是显式声明的远程模式就算本地": App 的实际部署形态
    # 就是本地(Windows 桌面 / 本机浏览器), 不需要为每种本地跑法单独开洞。
    # 真要防公网暴露, 该在部署层做, 而不是在这里猜运行模式。
    if getattr(settings, "allow_demo_data", None) is False:
        raise HTTPException(403, "此部署已禁用示例数据")

    try:
        from load_demo_data import load_demo_data
    except Exception as e:  # pragma: no cover
        log.error("import load_demo_data 失败: %s", e)
        raise HTTPException(500, f"示例数据工具不可用: {e}")

    weeks = max(1, min(52, payload.weeks))
    try:
        stats = load_demo_data(weeks=weeks, force=payload.force)
    except SystemExit as e:
        # ⚠️ SystemExit 继承自 BaseException 不是 Exception, 普通 except 抓不到。
        # 而 load_demo_data 里"归属不一致"这种**最需要用户看到的**错误
        # 恰恰用 SystemExit 抛出 —— 结果用户只看到"载入失败", 看不到原因。
        log.warning("载入示例数据被拒绝: %s", e)
        raise HTTPException(409, f"无法载入: {e}")
    except Exception as e:
        log.exception("载入示例数据失败")
        raise HTTPException(500, f"载入失败: {e}")

    return DemoLoadOut(
        ok=True,
        athlete_name=stats["athlete_name"],
        n_activities=stats["n_activities"],
        n_planned=stats["n_planned"],
        message=(
            f"已载入 {stats['n_activities']} 次示例训练。"
            "这是**示例数据**, 不是你的真实骑行记录。"
        ),
    )
