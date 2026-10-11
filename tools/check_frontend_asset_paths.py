#!/usr/bin/env python3
"""前端资源路径检查 —— V0.9.1

## 为什么需要这个

`vite.config.ts` 原来是 `base: "./"`, 于是 `index.html` 里写的是
`./assets/index-xxx.js`。

浏览器在 `/plan/calendar` 下把 `./assets/` 解析成 `/plan/assets/` ->
404 -> SPA fallback 返回 index.html(MIME `text/html`) ->
浏览器报 "Expected a JavaScript-or-Wasm module script" ->
**整个页面的 JS 一行都没执行**。

结果所有嵌套路由全是空白骨架: 没有数据、没有按钮、没有日历事件。
用户报的是"元素重叠""拖不动""按钮做了但看不见" —— 全都是这一个原因。

**根路径 `/` 恰好正常**(`./assets/` -> `/assets/`), 所以首页好好的,
一进子页面就空了。这也是它躲过好几轮 review 的原因。

## 为什么检查构建产物而不是 vite.config.ts

配置可能是对的但构建没跑, 也可能配置对了但有别的插件改写。
**用户拿到的是 `cycling_coach/static/index.html`, 不是配置文件。**
所以直接查产物 —— 这也顺带验证了"打包进去的确实是新构建"。

## 检查什么

1. `static/index.html` 存在(没构建过的话立刻报, 别让用户拿一个空壳包)
2. index.html 里的资源引用是**绝对路径**(`/assets/...`),
   不是相对路径(`./assets/` 或 `assets/`)
3. 磁盘上的文件真实存在(产物和引用对不上 = 部署后白屏)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "cycling_coach" / "static" / "index.html"


def main() -> int:
    if not INDEX.exists():
        print(f"❌ 没找到 {INDEX.relative_to(ROOT)}")
        print("   前端还没构建。跑:")
        print("       cd apps/web && npx vite build")
        print("   然后确认 vite 的 outDir 指向 ../../cycling_coach/static")
        return 1

    html = INDEX.read_text(encoding="utf-8")

    refs = re.findall(r'(?:src|href)="([^"]*assets/[^"]*)"', html)
    if not refs:
        print("❌ index.html 里没找到任何 assets 引用 —— 产物可能是空的")
        return 1

    print(f"检查 {len(refs)} 个资源引用 (static/index.html)")

    problems: list[str] = []

    for ref in refs:
        if ref.startswith("./") or not ref.startswith("/"):
            problems.append(
                f"{ref}\n"
                f"    → 相对路径。浏览器在 /plan/calendar 下会解析成"
                f" /plan/{ref.lstrip('./')}\n"
                f"    → 404 → SPA fallback 返回 index.html(MIME text/html)\n"
                f"    → 该页面的 JS 完全不执行, 渲染成空白骨架\n"
                f"    修法: vite.config.ts 的 base 改成 \"/\""
            )

    # 引用的文件必须真实存在
    static_dir = INDEX.parent
    for ref in refs:
        target = (ROOT / "cycling_coach" / "static" / ref.lstrip("/")).resolve()
        if not target.exists():
            problems.append(
                f"{ref} → 引用了不存在的文件 {target.name}\n"
                f"    → 部署后 404。要么重新构建, 要么产物没同步。"
            )

    if problems:
        print()
        for p in problems:
            print(f"❌ {p}\n")
        print("❌ 前端资源路径有问题。")
        print("   这些页面在用户机器上会是**空白**的, 而且不报任何错。")
        return 1

    print(f"✅ 全部 {len(refs)} 个资源引用都是绝对路径, 且文件存在")
    for ref in sorted(set(refs)):
        print(f"   {ref}")
    return 0


if __name__ == "__main__":
    sys.exit(main())