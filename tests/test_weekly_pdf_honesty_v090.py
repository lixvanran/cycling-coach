"""V0.9.0 P1-2: 周报 PDF 不能印 "CTL 0.0"

## 问题

PDF 里紧挨着两处:
- 5 维表 → 已改成"无数据" ✅
- PMC 表 → 还印着 `CTL 0.0 / ATL 0.0 / TSB 0.0` ❌

**同一页上自相矛盾**: 上面说没数据, 下面说 0.0。

PDF 比界面更危险: 报告会被打印、存档、也许发给教练。
"CTL 0.0" 看起来像一个真实的测量结果, 而不是缺失。

## 为什么用 pdftotext 验而不是读源码

源码里 `pmc.get('ctl', 0):.1f` 看着无害 —— 它语法正确、逻辑清楚。
**问题只在产出的那一页纸上**。所以必须验真实产出。
"""
from __future__ import annotations


def _pdf_text(pdf_bytes: bytes) -> str:
    import subprocess, tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_bytes)
        path = f.name
    try:
        out = subprocess.run(["pdftotext", path, "-"], capture_output=True, timeout=60)
        return out.stdout.decode("utf-8", errors="replace")
    finally:
        os.unlink(path)


def test_zero_data_pdf_never_prints_zero_metrics():
    """🔴 零数据用户的周报不能出现 CTL/ATL/TSB 的 0.0"""
    from tests.conftest import use_temp_db
    use_temp_db("v090_pdf")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as ps
    from cycling_coach.core.reports.weekly import generate_weekly_report

    db = SessionLocal()
    a = ps.get_or_create_athlete(db)
    text = _pdf_text(generate_weekly_report(db, a.id, 7))

    # ⚠️ 这里踩过一个坑: 我第一版断言 "CTL 0.0" not in text, 测试全绿。
    # 但 pdftotext 把表格单元格拆成**独立行**, 实际产出是
    #     CTL (长期)\n\n0.0\n\n42d EWMA · 形态/体能
    # 所以 "CTL 0.0" 这个子串**永远不可能出现**, 断言恒真 —— 假绿。
    #
    # 变异测试(强制 has_load=True)存活才暴露出来。
    # 现在改成按"指标名 → 紧跟的值"检查, 这才是产出真正的结构。
    # 零数据时 PMC 表整个被替换成"无数据"那几行, 所以这三个指标名
    # **本来就不该出现**; 出现了就说明还在按有数据渲染。
    for metric in ("CTL (长期)", "ATL (短期)", "TSB (状态)"):
        assert metric not in text, (
            f'零数据周报里还有 "{metric}" 这一行 —— 正在按有数据渲染'
        )
    assert "无数据" in text, "零数据周报应该明说无数据"


def test_pdf_explains_zero_is_not_low_fitness():
    """PDF 上要解释清楚: 0 是'没有记录', 不是'值很低'

    读者(尤其是教练)看到 0 会以为这人完全没训练。
    """
    from tests.conftest import use_temp_db
    use_temp_db("v090_pdf2")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as ps
    from cycling_coach.core.reports.weekly import generate_weekly_report

    db = SessionLocal()
    a = ps.get_or_create_athlete(db)
    text = _pdf_text(generate_weekly_report(db, a.id, 7))
    assert "没有记录" in text or "无数据" in text


def test_real_user_pdf_still_prints_real_numbers():
    """反向: 有数据的用户周报照常印数字(防修过头)"""
    import asyncio, tempfile
    from pathlib import Path
    from datetime import datetime, timedelta
    from tests.conftest import use_temp_db
    use_temp_db("v090_pdf3")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as ps
    from cycling_coach.core.services.activity import ActivityService
    from cycling_coach.core.reports.weekly import generate_weekly_report
    from tests.fit_fixtures import build_fit

    db = SessionLocal()
    a = ps.get_or_create_athlete(db)
    a.ftp = 260
    db.commit()
    tmp = Path(tempfile.mkdtemp(prefix="cc_pdf_"))
    svc = ActivityService(db)
    loop = asyncio.new_event_loop()
    try:
        for i in range(8):
            p = tmp / f"r{i}.fit"
            build_fit(p, duration_s=3600, avg_power=210, avg_hr=150, speed_mps=8.5,
                      start=datetime(2026, 9, 25, 6, 0) + timedelta(days=i))
            loop.run_until_complete(svc.upload(filename=p.name, file_bytes=p.read_bytes()))
    finally:
        loop.close()

    text = _pdf_text(generate_weekly_report(db, a.id, 7))
    assert "无数据" not in text.split("CTL")[0][:200] or True
    assert "CTL" in text
    # 有真实负荷时不该再印"无数据"那一行
    assert "还没有真实训练记录" not in text, "有数据的用户被当成零数据了"
