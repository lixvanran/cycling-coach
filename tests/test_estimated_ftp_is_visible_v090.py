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
    """[WEAK GUARD] 弱守卫, 独立审查实测过它可被绕过

    它只 grep 源码里的 `|| 250` / `|| 190` 两个字节面量。
    审查用现代运算符把假 250 原样加回来:

        const ftp = realFtp ?? estFtp ?? 250;      # 变异
        -> 4 passed, 0 failed

    任何别的写法(`?? 250` / 三元 / 常量表)都能绕过去, 而且它完全不看
    `cycling_coach/static/assets/*.js` —— 那才是用户实际加载的东西。

    为什么还留着: 成本为零, 至少能挡住"复制粘贴式"回归。
    真正的守卫是 `test_no_unguarded_ftp_label_v090.py`:
    它 grep **渲染出来的文案** 并剥掉注释, 审查实测能杀变异。

    **别把这个当门禁。** 真要确保, 应该上 React 渲染测试
    (需要 @testing-library/react + jsdom, 目前项目没装)。
    """
    import pathlib
    src = (pathlib.Path("apps/web/src") / "pages" / "ActivityDetail.tsx").read_text()
    code = "\n".join(
        l for l in src.splitlines() if not l.strip().startswith(("//", "*", "/*"))
    )
    for fake in ("|| 250", "|| 190"):
        assert fake not in code, f"前端代码里还留着假值兜底: {fake}"
