"""版本号必须处处一致

## 为什么需要这个脚本

V0.9.0 交付时发现三个地方版本号不一样:

    pyproject.toml      0.9.0   (后端)
    apps/web            0.8.1   (前端)
    apps/desktop        0.5.3   (桌面壳)

"统一版本号"这件事我以为做完了 —— 其实只改了后端。
用户看到的版本和后端对不上, 而**没有任何测试会发现这件事**。

新增一个检查的成本远低于下次再查一遍。
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> int:
    py = re.search(r'version = "([^"]+)"',
                   (ROOT / "pyproject.toml").read_text())
    if not py:
        print("❌ pyproject.toml 里找不到 version")
        return 1
    canonical = py.group(1)
    print(f"基准版本 (pyproject.toml): {canonical}")

    bad: list[tuple[str, str]] = []
    for rel in ("apps/web/package.json", "apps/desktop/package.json"):
        p = ROOT / rel
        if not p.exists():
            continue
        v = json.loads(p.read_text()).get("version")
        if v != canonical:
            bad.append((rel, str(v)))
        else:
            print(f"✅ {rel}: {v}")

    if bad:
        print("\n❌ 版本漂移:")
        for rel, v in bad:
            print(f"   {rel} = {v} (应为 {canonical})")
        print(f"\n修: 全部改成 {canonical}")
        return 1
    print("\n✅ 版本号处处一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
