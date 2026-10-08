"""V0.9.0-07: 估算 FTP 不能是"只写不读"的死字段

## 背景

后端很早就老实记录了 `tss_uses_estimated_ftp` / `ftp_used_for_tss`,
但**前端不读、AI prompt 不读、报告不读**。

于是诚实性只存在于数据库里 —— 用户和 AI 看到的都是一个
**看起来像实测值的估算 TSS**。

## 为什么这条最要紧

AI prompt 里写着"必须引用具体数据", 所以 AI 会把估算 TSS 当实测值引用,
再基于它给出训练强度建议。**用户在完全不知情的情况下照着骑车。**

比界面不显示严重得多。
"""
from __future__ import annotations


def _prompt(metrics: dict, athlete: dict) -> str:
    from cycling_coach.ai.prompts.analyze import build_analyze_prompt
    return build_analyze_prompt(metrics, athlete, 0, "")[1]


def test_ai_prompt_marks_estimated_tss():
    """🔴 核心: 估算 TSS 必须在 prompt 里标出来"""
    p = _prompt(
        {"tss": 111, "tss_uses_estimated_ftp": True, "ftp_used_for_tss": 190},
        {"name": "Rider", "ftp": None, "ftp_estimated": 190},
    )
    assert "估算 FTP" in p, "AI 完全不知道这个 TSS 是估算的 —— 它会当实测值引用"
    assert "190" in p, "应该说明是用哪个估算值算的"
    # 且必须禁止 AI 基于它下结论
    assert "不允许" in p, "prompt 里缺少'不许把估算值当实测'的硬约束"


def test_real_ftp_tss_is_not_marked_as_estimate():
    """反向: 真实 FTP 算的 TSS 不能被标成估算, 否则是另一种不诚实"""
    p = _prompt(
        {"tss": 90, "tss_uses_estimated_ftp": False, "ftp_used_for_tss": 300},
        {"name": "Rider", "ftp": 300, "ftp_estimated": 280},
    )
    assert "该 TSS 基于估算" not in p
    assert "300W(实测)" in p


def test_missing_tss_renders_as_no_data_not_none():
    """🔴 None 不能渲染成 'None' 或 '0'"""
    p = _prompt({"tss": None}, {"name": "Rider"})
    assert "训练压力 TSS: 无数据" in p
    assert ": None" not in p, "prompt 里出现了裸 None —— AI 会当成字面量"
    assert "FTP: 未设置" in p


def test_frontend_has_no_hardcoded_ftp_placeholder():
    """🔴 前端不许再有 `|| 250` 这种占位兜底

    这个值我在后端和 TrustPage 都清掉了, 但 ActivityDetail 漏了 ——
    于是"没测 FTP 的用户"在训练详情页会看到"基于 FTP 250W 计算"。
    """
    import pathlib
    src = (pathlib.Path("apps/web/src") / "pages" / "ActivityDetail.tsx").read_text()
    # 只看代码行 —— 注释里提到 `|| 250` 是为了说明"这里原来有", 不该被算成残留。
    # (第一版没排除注释, 结果自己的说明文字把自己测红了。)
    code = "\n".join(
        l for l in src.splitlines() if not l.strip().startswith(("//", "*", "/*"))
    )
    for fake in ("|| 250", "|| 190"):
        assert fake not in code, f"前端代码里还留着假值兜底: {fake}"
    assert "tss_uses_estimated_ftp" in code, "前端没消费估算标记 —— 用户看不到"
