"""V0.9.0-08: 前端不许出现无保护的 FTP 标签

## 背景: 我改了同一个文件三次, 漏了一处

`ActivityDetail.tsx` 里"基于 FTP xxxW"这个字符串出现过**两处**:

1. IF 卡片的 `hint` —— 我第一次改掉了
2. 功率区间标题下的副标题 —— **我漏了**

第二处是 Verifier 读代码时抓到的, 不是测试抓到的, 也不是我自查抓到的。
理由: 改第一处的时候我只搜了 `|| 250` 和 `ftp_label`, 没搜**渲染出来的文案**。

## 为什么这里最不能错

功率区间(Coggan 7 区)**本身就是按 FTP 推的**。
所以那句"基于 FTP 280W"不是装饰, 是用户理解整个图表的依据。
如果 280 是估算的, 却写成"基于 FTP", 用户会以为自己的区间是按真实
阈值算的 —— **然后照着这个区间训练**。

同类问题(都写死文案、忘了估算标记):
- IF 卡片 hint
- 功率区间副标题
- PowerCurveChart 的参考线标签
"""
from __future__ import annotations

import pathlib
import re

WEB = pathlib.Path(__file__).resolve().parent.parent / "apps" / "web" / "src"


def _code_lines(path: pathlib.Path) -> list[tuple[int, str]]:
    """返回 [(行号, 代码行)], 去掉注释"""
    out = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        st = line.strip()
        if st.startswith(("//", "/*", "*", "{/*")):
            continue
        out.append((i, line))
    return out


def test_activity_detail_has_no_unguarded_ftp_text():
    """🔴 核心: ActivityDetail 的代码里不许再有裸的 `基于 FTP {ftp}W`"""
    p = WEB / "pages" / "ActivityDetail.tsx"
    hits = [
        (i, l) for i, l in _code_lines(p)
        if re.search(r"基于\s*FTP\s*\{", l)
    ]
    assert not hits, (
        "这些地方还在把 `ftp` 直接渲染成'基于 FTP xxxW':\n  "
        + "\n  ".join(f"line {i}: {l.strip()}" for i, l in hits)
        + "\n\n`ftp` 是 realFtp ?? estFtp —— 没测 FTP 时它是**估算值**。"
          "功率区间按 FTP 推, 把估算说成实测, 用户会照着这个区间训练。"
          "改用 ftpLabel(它已经区分 实测/估算/未设置)。"
    )


def test_activity_detail_defines_and_uses_ftp_label():
    """反向: 必须真的用上区分三态的 ftpLabel, 不能只是定义了不用"""
    p = WEB / "pages" / "ActivityDetail.tsx"
    src = p.read_text(encoding="utf-8")
    assert "ftpLabel" in src, "没有 ftpLabel"
    # 至少在 JSX 里用一次
    uses = [l for _, l in _code_lines(p) if "{" in l and "ftpLabel" in l]
    assert uses, "ftpLabel 定义了但没在 JSX 里使用 —— 又是一个死变量"


def test_power_curve_chart_marks_estimated_ftp_line():
    """🔴 功率曲线图: 估算 FTP 的参考线必须标明并换色"""
    p = WEB / "components" / "PowerCurveChart.tsx"
    src = p.read_text(encoding="utf-8")
    assert "ftpIsEstimate" in src, (
        "PowerCurveChart 没有 ftpIsEstimate —— 估算 FTP 的参考线"
        "和实测的长得一样"
    )
    assert "估算 FTP" in src, "估算时标签应显示'估算 FTP xxxW'"
