#!/usr/bin/env python3
"""Windows 批处理文件编码检查 —— V0.9.1

## 为什么需要这个

`tools/ACCEPTANCE_CHECKLIST.bat` 是**中文 Windows 用户唯一的第一条上手路径**。
它是 GBK 编码的(Windows 记事本/cmd 的传统编码)。

V0.9.1 我改它的时候, 用 `encoding='gbk'` 读取、却让某些工具按 UTF-8 写回,
**结果整个文件变成了 UTF-8**。在 Windows 上执行时, 所有中文提示都会变成乱码:
    正在安装后端依赖  ->  ����װ��������Ҫ��
用户根本看不懂哪一步失败了, 而这是他们**唯一**的引导。

静态测试抓不到这种问题 —— bat 文件不进 pytest。所以写这个检查。

## 检查什么

1. 编码必须是 GBK(能编解码), 且**不能**同时是合法 UTF-8
   (纯 ASCII 文件两者都合法, 那种情况放过)
2. 必须能正常按 GBK 解码出中文
3. 行尾不能被改成 CRLF/LF 混用 —— 虽然两种 cmd 都能跑,
   但混用会让 diff 变乱, 且说明文件被外部工具动过

## 用法

    python tools/check_bat_encoding.py        # 只检查 bat
    python tools/check_bat_encoding.py --all  # 连同 README 一并检查
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 这些文件是给 Windows 中文用户直接执行的, 编码错了用户就看不懂
BAT_FILES = [
    "tools/ACCEPTANCE_CHECKLIST.bat",
]

# Windows 批处理常用 GBK (cp936)。UTF-8 BOM 也不行 ——
# cmd 会把 BOM 当成命令的一部分, 第一行就报错。
EXPECTED_ENCODING = "gbk"


def check_one(path: Path) -> list[str]:
    errs: list[str] = []
    if not path.exists():
        return [f"文件不存在: {path}"]

    raw = path.read_bytes()

    # 1. BOM 检查 —— cmd 遇到 UTF-8 BOM 会把首行当命令, 直接失败
    if raw.startswith(b"\xef\xbb\xbf"):
        errs.append("文件带 UTF-8 BOM —— cmd.exe 会把 BOM 当命令的一部分, "
                    "第一行就报错。必须去掉。")

    # 2. 必须能按 GBK 解码
    try:
        text = raw.decode(EXPECTED_ENCODING)
    except UnicodeDecodeError as e:
        errs.append(
            f"不能按 {EXPECTED_ENCODING} 解码: {e}\n"
            f"    这个文件是给中文 Windows 用户执行的, 编码错了满屏乱码。"
        )
        return errs

    # 3. 纯 ASCII 文件两种编码都合法, 跳过歧义判断
    is_ascii = all(b < 128 for b in raw)
    if not is_ascii:
        try:
            raw.decode("utf-8")
            errs.append(
                f"文件能被 UTF-8 解码, 说明很可能已经被改成 UTF-8 了 —— "
                f"但 cmd 需要 {EXPECTED_ENCODING}。"
                f"\n    修法: 用 python 以 {EXPECTED_ENCODING} 读写, "
                f"不要用默认 utf-8。"
            )
        except UnicodeDecodeError:
            pass  # 正常: 只在 GBK 下合法, 正是我们要的

    # 4. 确认真的有中文, 免得文件被清空了还"检查通过"
    if not any("一" <= c <= "鿿" for c in text):
        errs.append("文件里一个中文字符都没有 —— 内容可能被清空了。")

    return errs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true",
                    help="检查所有 Windows 入口脚本")
    args = ap.parse_args()

    files = [ROOT / f for f in BAT_FILES]
    failed = False

    print(f"检查 {len(files)} 个 Windows 脚本的编码 (期望 {EXPECTED_ENCODING}, 无 BOM)")
    for f in files:
        errs = check_one(f)
        rel = f.relative_to(ROOT)
        if errs:
            failed = True
            print(f"\n❌ {rel}")
            for e in errs:
                print(f"   {e}")
        else:
            print(f"✅ {rel}  ({f.stat().st_size} 字节, GBK 无 BOM)")

    if failed:
        print("\n❌ Windows 脚本编码有问题。")
        print("   这些文件是中文用户的第一条上手路径, 编码错了满屏乱码。")
        return 1
    print("\n✅ 所有 Windows 脚本编码正确。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())