#!/usr/bin/env python3
"""文档引用的本地资源必须真的入库 —— V0.9.1

## 为什么需要这个

2026-10-18 打包验证时抓到的:

1. `.gitignore` 里有 `screenshots/`, 匹配**任何层级**的同名目录
2. 于是 `docs/screenshots/` 也被挡住了
3. README 里写了 `<img src="docs/screenshots/dashboard.png">`
4. 图片从没进过 git -> 打包脚本用 `git ls-files` 收文件 -> 收不到
5. **用户拿到的包里 README 是裂图**

整条链上没有任何一步会报错:
- Markdown 语法合法
- 图片在磁盘上(本地看是好的)
- README 渲染在本地没问题
- 打包器没有缺失文件 —— 它只收它知道的

**裂图只在用户手里才出现。**

## 检查什么

README.md 里所有本地资源引用(图/链接), 对应的文件必须:
1. 磁盘上存在
2. **被 git 跟踪**(否则打包时收不到)

只查 README 和 docs/ 下的 Markdown, 不查全仓库 ——
这个检查针对的是"文档和资源入库不一致"这一类。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MD_FILES = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]

# 三种引用形式都要查, 少一种就有静默漏网:
#   1. Markdown 图片   ![alt](path)
#   2. Markdown 链接   [text](path)
#   3. HTML <img src>  —— README 里并排放图的表格用的就是它
#
#   我第一版只写了前两种, 于是 <img src> 形式的图**根本没进检查**。
#   拿一张 HTML 写法的图做变异 -> 检查依然通过 -> **检查是摆设**。
#
#   和 CLAUDE.md 铁律二("按读取点枚举, 不按印象枚举")同一个坑。
#   教训: 检查脚本本身也要做变异测试, 否则你不知道它在检查什么。
RE_IMG = re.compile(r'!\[[^\]]*\]\(([^)\s]+)')
RE_LINK = re.compile(r'(?<!\!)\[[^\]]*\]\(([^)\s]+)')
RE_HTML_IMG = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)
RE_HTML_SRC = re.compile(r'<(?:script|a|link)[^>]+(?:src|href)=["\']([^"\']+)["\']', re.I)


def is_external(url: str) -> bool:
    return url.startswith(("http://", "https://", "mailto:", "#", "data:"))


def git_tracked(rel: str) -> bool:
    r = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--error-unmatch", rel],
        capture_output=True,
    )
    return r.returncode == 0


def main() -> int:
    if not MD_FILES:
        print("✅ 没有 Markdown 文件要检查")
        return 0

    problems: list[str] = []
    checked = 0

    for md in MD_FILES:
        if not md.exists():
            continue
        text = md.read_text(encoding="utf-8")
        refs = (set(RE_IMG.findall(text)) | set(RE_LINK.findall(text))
                | set(RE_HTML_IMG.findall(text)) | set(RE_HTML_SRC.findall(text)))
        base = md.parent

        for ref in refs:
            if is_external(ref):
                continue
            # 去掉锚点
            path_part = ref.split("#")[0].strip()
            if not path_part:
                continue
            checked += 1

            target = (base / path_part).resolve()
            try:
                rel = target.relative_to(ROOT.resolve())
            except ValueError:
                problems.append(
                    f"{md.relative_to(ROOT)}: 引用 `{ref}` 指向仓库外"
                )
                continue

            if not target.exists():
                problems.append(
                    f"{md.relative_to(ROOT)}: 引用 `{ref}` 但文件不存在"
                )
            elif not git_tracked(str(rel)):
                # 关键: 本地有, 但没进 git -> 打包时收不到 -> 用户裂图
                r = subprocess.run(
                    ["git", "-C", str(ROOT), "check-ignore", "-v", str(rel)],
                    capture_output=True, text=True,
                )
                reason = ""
                if r.returncode == 0 and r.stdout.strip():
                    reason = f" (.gitignore: {r.stdout.strip().split()[0]})"
                problems.append(
                    f"{md.relative_to(ROOT)}: 引用 `{ref}` 存在但**未被 git 跟踪**{reason}"
                    f"\n    -> 打包脚本用 git ls-files 收文件, 用户会拿到裂图"
                )

    print(f"检查 {len(MD_FILES)} 个 Markdown, {checked} 处本地引用")

    if problems:
        print()
        for p in problems:
            print(f"❌ {p}\n")
        print("❌ 文档引用的资源没有全部入库。")
        print("   本地看着正常, 用户拿到包里是裂图 —— 不会报错, 只会静默坏掉。")
        return 1

    print("✅ 所有本地资源引用都存在且已被 git 跟踪")
    return 0


if __name__ == "__main__":
    sys.exit(main())