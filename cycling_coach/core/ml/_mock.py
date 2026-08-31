"""Mock FTP 预测模型

无真实训练数据时的占位 — 用规则预测 FTP
公式: current_ftp = athlete.ftp + adjust(tsb, ramp_rate)

V0.7.6: 简单规则, V0.7.7+ 接真实 GBM 模型
"""
from __future__ import annotations

import numpy as np


class MockFTPModel:
    """简单 mock: 用规则预测 FTP

    公式:
    - base = Athlete.ftp
    - adjust:
        TSB > 5 (恢复好) → +5W
        TSB < -10 (疲劳) → -5W
        -5 < ramp < 5 (稳定) → +2W
    """

    def __init__(self, base_ftp: int = 250):
        self.base_ftp = base_ftp

    def predict(self, X) -> np.ndarray:
        # X is [N, 12]: ctl,atl,tsb,ramp_rate,sleep_h,hrv_ms,rpe,
        #              distance_m,duration_s,tss,normalized_power,intensity_factor
        predictions = []
        for row in X:
            ctl, atl, tsb, ramp, sleep, hrv, rpe, dist, dur, tss, np_, if_ = row[:12]
            adjust = 0
            if tsb > 5:
                adjust += 5
            elif tsb < -10:
                adjust -= 5
            if -5 < ramp < 5:
                adjust += 2
            predictions.append(self.base_ftp + adjust)
        return np.array(predictions, dtype=np.float32)
