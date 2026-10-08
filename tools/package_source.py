"""打包 Windows 交付源码 zip

## 为什么需要单独一个脚本

三样东西**不在 git 里但必须进 zip**, 漏掉任何一样都会让用户拿到一个跑不起来的包:

1. `cycling_coach/static/` — 前端构建产物。
   .gitignore 排除了它(合理的: 构建产物不该进版本控制),
   但 Windows 用户**不会装 Node.js**, 拿到的包必须自带界面。
   **漏了 = 双击打开是白页。**
2. `kb_source/markdown/` — AI 知识库。
   在 git 里, 但**用 `git ls-files` 逐行读会在超长路径上被换行截断**
   (最长 229 字符), 静默丢掉 359 个知识库文件。
   → 必须用 `git ls-files -z`。
3. 任何被 .gitignore 排除、但运行时需要的东西。

## 护栏

`verify()` 会检查三样都在, 少一样直接抛错 —— 打包后必须过这一关。
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def collect() -> list[tuple[pathlib.Path, str]]:
    """返回 [(磁盘路径, zip 内相对路径)]"""
    out: list[tuple[pathlib.Path, str]] = []
    seen: set[str] = set()

    # -z: NUL 分隔。逐行读会被超长路径 / 含换行的名字截断, 静默丢文件。
    for raw in _git("ls-files", "-z").split(b"\0"):
        if not raw:
            continue
        rel = raw.decode()
        p = ROOT / rel
        if p.is_file() and rel not in seen:
            seen.add(rel)
            out.append((p, rel))

    # 前端构建产物: 被 gitignore, 但 Windows 用户要的是开箱即用
    static = ROOT / "cycling_coach" / "static"
    if static.is_dir():
        for p in static.rglob("*"):
            if p.is_file():
                rel = p.relative_to(ROOT).as_posix()
                if rel not in seen:
                    seen.add(rel)
                    out.append((p, rel))
    return out


REQUIRED = [
    "cycling_coach/static/index.html",   # 没有它 = 白页
    "cycling_coach/api/main.py",
    "tools/start.py",
]


def verify(files: list[tuple[pathlib.Path, str]]) -> None:
    names = {rel for _, rel in files}
    missing = [r for r in REQUIRED if r not in names]
    kb = [n for n in names if n.startswith("kb_source/")]
    if missing:
        raise SystemExit(
            "打包中止 —— 缺这些必需文件, 用户的包会是坏的:\n  "
            + "\n  ".join(missing)
            + "\n\n(前端是否构建过? 跑 cd apps/web && npm run build)"
        )
    if len(kb) < 100:
        raise SystemExit(
            f"打包中止 —— 知识库只有 {len(kb)} 个文件, 应该是 361。\n"
            "AI 检索会没有资料。检查 git ls-files -z 是否被破坏。"
        )
    print(f"✅ 护栏通过: 前端已包含, 知识库 {len(kb)} 个文件")


def build(dest: pathlib.Path) -> pathlib.Path:
    files = collect()
    verify(files)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for disk, rel in files:
            z.write(disk, rel)
    with zipfile.ZipFile(dest) as z:
        if z.testzip() is not None:
            raise SystemExit("zip 完整性校验失败")
        longest = max(len(n) for n in z.namelist())
    if longest > 240:
        print(
            f"⚠️  最长路径 {longest} 字符。Windows 上限 260, 加上解压目录名后余量不多,\n"
            f"    提醒用户解压到短路径 (如 C:\\cc), 别放在很深的目录里。"
        )
    print(f"✅ {dest}  {len(files)} 个文件  {dest.stat().st_size/1e6:.1f} MB")
    return dest


if __name__ == "__main__":
    target = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "cycling-coach-source.zip"
    build(target)
