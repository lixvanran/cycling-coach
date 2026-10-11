#!/usr/bin/env python3
"""清理历史遗留的假 FTP —— V0.9.1

## 为什么需要这个脚本

V0.9.0 之前, `get_or_create_athlete()` 在建车手时会写死
`ftp=250, max_hr=185`。这些值**从来没被用户确认过**, 是为了让
IF/TSS/区间能算出个数字而编的。

V0.9.0 已经改成 `ftp=None`, 但**已经写进用户数据库的 250 还留着**。
后果是:
  - 界面上显示"FTP 250W", 用户以为是自己的真实功率
  - 所有 IF/TSS/功率区间都是按这个假值算的, 全错
  - 而用户根本没机会纠正它(因为界面显示"已设置")

这是**数据可信度问题**, 不是显示问题 —— 假数据比没数据更糟。

## 为什么默认不动它

**不能自动改**。因为真的有人 FTP 就是 250。
自动清空会把这些用户的正确数据也抹掉。

所以: 只报告, 由用户确认后才改。加 `--apply` 才真正写入。

## 用法

    # 只看, 不改(安全, 可以随便跑)
    python tools/migrate_placeholder_ftp.py

    # 确认后真正清理
    python tools/migrate_placeholder_ftp.py --apply

    # 明确保留某个人(他确认过 250 就是真的)
    python tools/migrate_placeholder_ftp.py --apply --keep 1
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# V0.9.0 之前的写死值。改动这里要同步改 CLAUDE.md 的诚实性清单。
PLACEHOLDER_FTP = 250
PLACEHOLDER_MAX_HR = 185


def main() -> int:
    ap = argparse.ArgumentParser(
        description="清理历史遗留的假 FTP(250) / 假最大心率(185)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--apply", action="store_true",
                    help="真正写入数据库(默认只报告)")
    ap.add_argument("--keep", type=int, action="append", default=[],
                    help="这个 athlete_id 的 FTP 是真的, 不要清(可多次)")
    ap.add_argument("--workspace", type=str, default=None,
                    help="数据目录, 默认取 WORKSPACE_DIR 环境变量")
    args = ap.parse_args()

    if args.workspace:
        os.environ["WORKSPACE_DIR"] = args.workspace

    from cycling_coach.data.sqlite.database import init_db, SessionLocal
    from cycling_coach.data.sqlite.models import Athlete

    init_db()
    db = SessionLocal()

    athletes = db.query(Athlete).order_by(Athlete.id).all()
    if not athletes:
        print("库里还没有车手, 无需处理。")
        return 0

    # 只找"正好等于占位值"的, 不碰用户自己填的数
    suspects = [
        a for a in athletes
        if (a.ftp == PLACEHOLDER_FTP or a.max_hr == PLACEHOLDER_MAX_HR)
        and a.id not in args.keep
    ]

    if not suspects:
        print(f"✅ 检查了 {len(athletes)} 个车手, 没有发现历史遗留的假 FTP/心率。")
        return 0

    print(f"⚠️ 发现 {len(suspects)} 个车手带历史遗留的占位值:")
    print(f"    (FTP={PLACEHOLDER_FTP} / 最大心率={PLACEHOLDER_MAX_HR})")
    print()
    for a in suspects:
        marks = []
        if a.ftp == PLACEHOLDER_FTP:
            marks.append("ftp=250(编的)")
        if a.max_hr == PLACEHOLDER_MAX_HR:
            marks.append("max_hr=185(编的)")
        n_acts = db.query(Athlete).filter(Athlete.id == a.id).count()
        print(f"  #{a.id} {a.name!r:16} {' + '.join(marks)}  "
              f"(名下 {n_acts} 个车手记录)")
    print()

    if not args.apply:
        print("这些值从没被确认过, 会让 IF/TSS/功率区间全部失真。")
        print("确认要清理就跑:")
        print(f"    {Path(sys.argv[0]).name} --apply")
        print()
        print("如果你确认某个人的 250 就是真实 FTP, 用 --keep <id> 保留:")
        print(f"    {Path(sys.argv[0]).name} --apply --keep 1")
        return 1

    for a in suspects:
        if a.ftp == PLACEHOLDER_FTP:
            a.ftp = None
        if a.max_hr == PLACEHOLDER_MAX_HR:
            a.max_hr = None
    db.commit()

    print(f"✅ 已清空 {len(suspects)} 个车手的占位 FTP/心率。")
    print("   现在他们的 IF/TSS 会显示为'无数据', 直到在")
    print("   「个人画像」页填入真实 FTP —— 这是正确的: 宁可没有, 也不要假的。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())