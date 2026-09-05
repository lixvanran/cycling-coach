"""V0.8.0: 训练数据导出 CLI

用途: 训练 ML 模型 (ftp-predictor) 时, 从 cycling-coach DB 导出 20 维特征 + 标签

用法:
    python -m cycling_coach.cli.export_features --out features.parquet
    python -m cycling_coach.cli.export_features --out features.csv --window-days 14
    python -m cycling_coach.cli.export_features --out f.parquet --with-ftp-targets

数据流:
    Activity (窗口聚合) + FTPTest (最近一次作为 target) → 20 维特征 + 1 维 target

输出列对齐 ftp-predictor:
    distance, moving_time, average_heartrate,
    HR Zone 1-5,
    kilojoules,
    Power Zone 1-11,
    ftp_target      # 来自最近的 FTPTest (按 athlete + 时间匹配)

ftp-predictor 消费方:
    import pandas as pd
    df = pd.read_parquet('features.parquet')
    feature_cols = [c for c in df.columns if c != 'ftp_target']
    X = df[feature_cols].values
    y = df['ftp_target'].values
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from cycling_coach.core.ml.feature_pipe import (
    build_feature_row,
    FEATURE_COLUMNS,
    DEFAULT_WINDOW_DAYS,
)
from cycling_coach.data.sqlite.database import SessionLocal
from cycling_coach.data.sqlite.models import Activity, Athlete, FTPTest

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def _find_ftp_target(
    db: Session, athlete_id: int, ref_date: datetime, lookback_days: int = 30
) -> Optional[int]:
    """找 ref_date 前 [lookback_days] 天内最近的 FTPTest, 返回 ftp_w (W)"""
    cutoff = ref_date - timedelta(days=lookback_days)
    test = (
        db.query(FTPTest)
        .filter(FTPTest.athlete_id == athlete_id)
        .filter(FTPTest.test_date <= ref_date)
        .filter(FTPTest.test_date >= cutoff)
        .order_by(FTPTest.test_date.desc())
        .first()
    )
    if test:
        return int(test.ftp_w)
    return None


def export_features(
    out_path: str,
    window_days: int = DEFAULT_WINDOW_DAYS,
    with_ftp_targets: bool = True,
    only_with_targets: bool = False,
    min_window_activities: int = 3,
    max_athletes: Optional[int] = None,
) -> int:
    """导出训练数据到 parquet / csv

    Args:
        out_path: 输出文件路径 (.parquet / .csv)
        window_days: 特征聚合窗口 (默认 14 天, 对齐 ftp-predictor)
        with_ftp_targets: 是否 JOIN FTPTest 取目标值
        only_with_targets: 只导出有 FTP 目标的行 (训练时用)
        min_window_activities: 窗口内最少活动数, 太少的不导出
        max_athletes: 最多处理几个 athlete (调试用)

    Returns:
        导出行数
    """
    db = SessionLocal()
    try:
        athletes = db.query(Athlete).all()
        if max_athletes:
            athletes = athletes[:max_athletes]
        logger.info(f"处理 {len(athletes)} 个 athlete, 窗口={window_days}天")

        rows = []
        skipped_no_activity = 0
        skipped_no_target = 0
        skipped_low_count = 0

        for athlete in athletes:
            # 拿该 athlete 全部活动
            activities = (
                db.query(Activity)
                .filter(Activity.athlete_id == athlete.id)
                .order_by(Activity.start_time)
                .all()
            )
            if not activities:
                skipped_no_activity += 1
                continue

            # 按窗口滑动: 每个活动作为 ref_date, 取前 [window_days] 天窗口
            for ref_activity in activities:
                ref_date = ref_activity.start_time
                # 窗口内活动
                window_start = ref_date - timedelta(days=window_days)
                window_acts = [
                    a for a in activities
                    if window_start <= a.start_time <= ref_date
                ]
                if len(window_acts) < min_window_activities:
                    skipped_low_count += 1
                    continue

                # 拼 20 维特征
                try:
                    values, _ = build_feature_row(
                        db,
                        athlete_id=athlete.id,
                        ref_date=ref_date,
                        window_days=window_days,
                    )
                except ValueError:
                    continue

                row = dict(zip(FEATURE_COLUMNS, values))
                row["athlete_id"] = athlete.id
                row["ref_date"] = ref_date
                row["ref_activity_id"] = ref_activity.id

                if with_ftp_targets:
                    target = _find_ftp_target(db, athlete.id, ref_date)
                    if target is None:
                        if only_with_targets:
                            skipped_no_target += 1
                            continue
                        target = np.nan
                    row["ftp_target"] = target

                rows.append(row)

        if not rows:
            logger.warning("无数据可导出")
            return 0

        df = pd.DataFrame(rows)
        # 调整列顺序: features + meta + target 在最末
        meta_cols = ["athlete_id", "ref_date", "ref_activity_id"]
        target_col = ["ftp_target"] if with_ftp_targets else []
        df = df[FEATURE_COLUMNS + meta_cols + target_col]

        # 写文件
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.suffix == ".parquet":
            df.to_parquet(out, index=False)
        elif out.suffix == ".csv":
            df.to_csv(out, index=False)
        else:
            raise ValueError(f"不支持的输出格式: {out.suffix} (要 .parquet 或 .csv)")

        logger.info(
            f"导出 {len(df)} 行 → {out} "
            f"(skip: no_act={skipped_no_activity}, no_target={skipped_no_target}, "
            f"low_count={skipped_low_count})"
        )
        return len(df)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="导出 cycling-coach 训练数据 (20 维特征 + FTP target) 给 ftp-predictor"
    )
    parser.add_argument(
        "--out", required=True, help="输出文件路径 (.parquet / .csv)"
    )
    parser.add_argument(
        "--window-days", type=int, default=DEFAULT_WINDOW_DAYS,
        help=f"特征聚合窗口 (天), 默认 {DEFAULT_WINDOW_DAYS}",
    )
    parser.add_argument(
        "--with-ftp-targets", action="store_true", default=True,
        help="JOIN FTPTest 拿 ftp_w 目标值 (默认 True)",
    )
    parser.add_argument(
        "--only-with-targets", action="store_true", default=False,
        help="只导出有 FTP 目标的行 (训练时用)",
    )
    parser.add_argument(
        "--min-window-activities", type=int, default=3,
        help="窗口内最少活动数 (默认 3)",
    )
    parser.add_argument(
        "--max-athletes", type=int, default=None,
        help="最多处理几个 athlete (调试用)",
    )
    args = parser.parse_args()
    n = export_features(
        out_path=args.out,
        window_days=args.window_days,
        with_ftp_targets=args.with_ftp_targets,
        only_with_targets=args.only_with_targets,
        min_window_activities=args.min_window_activities,
        max_athletes=args.max_athletes,
    )
    sys.exit(0 if n > 0 else 1)


if __name__ == "__main__":
    main()
