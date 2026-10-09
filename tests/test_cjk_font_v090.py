"""V0.9.0-08: 周报 PDF 的中文字体必须真的可用

## 背景: 一个交付目标与实现完全脱节的 bug

产品交付目标是 **Windows 桌面**, 而周报的字体候选清单里
**只有 Linux 路径**:

    /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc
    /usr/share/fonts/truetype/wqy/wqy-zenhei.ttc
    /usr/share/fonts/truetype/arphic/ukai.ttc

Windows 上这三条一个都不存在 -> 注册全部失败 -> 静默退回
`Helvetica` -> **周报 PDF 里的中文全是乱码**。

用户拿到的是一份没法看的周报, 而 `diagnose.py` 只报 WARN 不报 FAIL,
所以没有任何门禁会拦住它。

## 第二个坑: .ttc 是字体集合

NotoSansCJK-Regular.ttc 确实存在, 但 reportlab 的 TTFont 报
`postscript outlines are not supported` —— **文件在 ≠ 能用**。
`.ttc` 是一组字体的集合, 必须给 `subfontIndex` 指定用里面第几个。
"""
from __future__ import annotations


def test_font_candidates_include_windows_paths():
    """🔴 核心: 候选清单必须包含 Windows 系统字体路径"""
    from cycling_coach.core.reports.weekly import _FONT_CANDIDATES
    paths = [p for p, _, _ in _FONT_CANDIDATES]
    win = [p for p in paths if "Windows" in p]
    assert win, (
        "字体候选里没有任何 Windows 路径 —— 交付目标是 Windows, "
        "这些路径在目标机器上一个都不存在, 周报中文必然乱码"
    )
    # 微软雅黑/宋体 是 Windows 必带的中文字体
    assert any("msyh" in p.lower() or "simsun" in p.lower() for p in win)


def test_all_candidates_are_triples():
    """🔴 每条候选都必须是 3 元组 (路径, 名称, ttc 子字体序号)

    我第一版写的时候漏了两条 (simhei / Deng), 结果函数直接
    `ValueError: not enough values to unpack` —— 整个周报生成崩掉。
    """
    from cycling_coach.core.reports.weekly import _FONT_CANDIDATES
    for c in _FONT_CANDIDATES:
        assert len(c) == 3, f"候选必须是 3 元组, 这条只有 {len(c)} 个: {c}"
        assert isinstance(c[2], int), f"第 3 项必须是 subfontIndex 整数: {c}"


def test_registered_font_can_actually_render_chinese():
    """🔴 核心: 注册成功后字体必须真能排出中文的宽度

    静默退回 Helvetica 时 `stringWidth('训练负荷分析')` 仍然返回一个数,
    但那是按"豆腐块"宽度算的 —— 所以要断言**每字宽度接近字号**。
    """
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from cycling_coach.core.reports.weekly import _register_chinese_font

    font = _register_chinese_font()
    assert font != "Helvetica", (
        "退回 Helvetica 了 —— 周报 PDF 的中文会是乱码。"
        "Windows: 确认 C:\\Windows\\Fonts\\msyh.ttc 存在; "
        "Linux: 装 fonts-noto-cjk 或 fonts-wqy-zenhei"
    )
    w = stringWidth("训练负荷分析", font, 12)
    per_char = w / 6
    assert 10 <= per_char <= 14, (
        f"每字宽度 {per_char:.1f}pt (12pt 字号下应约 12pt) —— "
        f"字体 {font} 可能没有真正生效"
    )
