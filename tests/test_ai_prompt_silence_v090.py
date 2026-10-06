"""V0.9.0: AI prompt 静默失效防护

## 这组测试在防什么

Verifier 抓到的 P1, 严重程度其实接近 P0:

> `_format_acwr_block` 读 `acwr.get("today")`, 但 `context.py` 给的是扁平 dict。
> 于是 `today` 恒为 None → return "" → **ACWR 区块从来没进过 prompt**。

这不是"某个字段算错", 是**对所有人静默失效**:
- 用户有完整训练数据, AI 依然不知道他的急慢性负荷比
- 没有异常, 没有日志, 测试全绿

> **静默失效比崩溃危险。** 崩溃会告诉你, 静默失效会让你相信它在工作。

同一个文件里还有第二处同类问题: `unknown` 阶段被原样丢给模型,
模型会把 "阶段: unknown" 当成一个真实阶段类型来推理, 甚至顺着它编训练建议。

## 这组测试的方法

**不用 mock 断言 mock** —— 而是直接断言"渲染结果里有没有那个数字"。
这样即使 context 以后再改形状, 测试也会跟着对。
"""
from __future__ import annotations

import pytest

from cycling_coach.ai.prompts.chat import _format_acwr_block, _format_phase_block


# ── ACWR ────────────────────────────────────────────────────────


def test_acwr_reaches_prompt_with_flat_context():
    """🔴 核心回归: context.py 给的扁平形状必须能渲染出 ACWR

    这是修复前的实际形状(acwr={acwr, acute, chronic, zone, risk, risk_label})。
    修复前这段返回空字符串。
    """
    flat = {"acwr": 1.05, "acute": 52.0, "chronic": 49.5,
            "zone": "sweet_spot", "risk": "low", "risk_label": "甜蜜区"}
    out = _format_acwr_block(flat)
    assert "ACWR" in out, "扁平形状渲染不出 ACWR 区块 —— 静默失效"
    assert "1.05" in out, f"渲染了但没有真实比值: {out!r}"


def test_acwr_still_accepts_nested_shape():
    """旧形状也要认 —— 防御 context 以后再改一次结构"""
    nested = {"today": {"acwr": 1.25, "acute_avg": 50, "chronic_avg": 40}}
    out = _format_acwr_block(nested)
    assert "1.25" in out


def test_acwr_absent_is_omitted_not_faked():
    """真没数据时省略, 不能编一个 0.00 或者"正常"出来"""
    assert _format_acwr_block({}) == ""
    assert _format_acwr_block({"acwr": None, "acute": 0, "chronic": 0}) == ""


def test_acwr_does_not_fall_back_to_zero():
    """🔴 缺 ratio 时不能拿 0 当 ratio

    ratio=0 会渲染成 "ACWR 0.00 (可能掉状态)" —— 一个凭空来的训练学结论,
    恰恰是整个 V0.9.0 在消灭的东西。
    """
    out = _format_acwr_block({"acute": 0, "chronic": 0, "zone": None})
    assert "0.00" not in out
    assert out == ""


def test_acwr_risk_band_is_rendered():
    """真实比值要带风险判断, 不只是数字"""
    out = _format_acwr_block({"acwr": 1.6, "acute": 80, "chronic": 50})
    assert "1.60" in out
    assert "风险" in out or "过训" in out


# ── 阶段 ────────────────────────────────────────────────────────


def test_unknown_phase_is_not_shown_as_a_real_phase():
    """🔴 unknown 不能被当成一个真实阶段丢给模型

    修复前会渲染 "阶段: unknown - 数据不足"。模型看到"阶段: unknown",
    可能把它当成一个(奇怪的)阶段类型来推理, 甚至顺着它编训练处方。
    """
    out = _format_phase_block({
        "phase_type": "unknown", "label": "数据不足，无法判断阶段",
        "confidence": 0.0, "reasons": [],
    })
    assert "阶段: unknown" not in out, f"把 unknown 当成真阶段了: {out!r}"
    assert "数据不足" in out
    # 必须明确禁止模型编造 —— 这是这段文本存在的全部意义
    assert "不要" in out


def test_real_phase_still_renders_normally():
    """反向: 有数据的用户阶段块必须照常渲染(防修过头)"""
    out = _format_phase_block({
        "phase_type": "base", "suggested_label": "基础期",
        "confidence": 0.8, "reasons": ["CTL 稳定上升"],
    })
    assert "基础期" in out
    assert "80%" in out


def test_taper_is_understood_as_taper():
    """减量期必须被解释成"降量蓄能", 而不是原样丢一个 taper 给模型"""
    out = _format_phase_block({
        "phase_type": "taper", "suggested_label": "减量期",
        "confidence": 0.9, "reasons": [],
    })
    assert "Taper" in out or "降量" in out


def test_suggested_field_names_are_accepted():
    """🔴 字段名兼容: context 写的是 suggested_type/suggested_label

    如果哪天只认 phase_type/label, 阶段块会静默变空 —— AI 就不知道用户在
    哪个阶段了。这条钉住两个名字都认。
    """
    out = _format_phase_block({
        "suggested_type": "build", "suggested_label": "强化期",
        "confidence": 0.7, "reasons": [],
    })
    assert "强化期" in out


def test_empty_phase_omits_block():
    """没有阶段信息就整块省略, 不能输出半截"""
    assert _format_phase_block({}) == ""
    assert _format_phase_block(None) == ""
