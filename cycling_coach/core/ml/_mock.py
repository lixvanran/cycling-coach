"""Mock FTP 预测模型

无真实训练数据时的占位 — 用规则预测 FTP
公式: current_ftp = athlete.ftp + adjust(hr_zone4_time, hr_zone5_time, kilojoules)

V0.7.6: 简单规则, V0.7.7+ 接真实 GBM 模型
V0.8.0: 12 维 → 20 维, 改用 ftp-predictor 风格的特征
"""
from __future__ import annotations

import numpy as np

from .feature_pipe import FEATURE_COLUMNS


class MockFTPModel:
    """简单 mock: 用规则预测 FTP

    公式 (V0.8.0, 跟 ftp-predictor 思路一致):
    - base = Athlete.ftp
    - adjust:
        HR Zone 4 时间越多 → + 阈值训练多, FTP 涨
        HR Zone 5 时间过多 → - 高强度恢复不够
        kilojoules 高 → + 训练量足
    """

    def __init__(self, base_ftp: int = 250):
        self.base_ftp = base_ftp

    def predict(self, X) -> np.ndarray:
        # X is [N, 20]: 跟 FEATURE_COLUMNS 顺序
        # distance, moving_time, average_heartrate,
        # HR Zone 1-5, kilojoules,
        # Power Zone 1-11
        col_idx = {c: i for i, c in enumerate(FEATURE_COLUMNS)}
        i_hz4 = col_idx["HR Zone 4"]
        i_hz5 = col_idx["HR Zone 5"]
        i_kj = col_idx["kilojoules"]
        i_mt = col_idx["moving_time"]
        i_pz4 = col_idx["Power Zone 4"]  # 阈值区
        i_pz5 = col_idx["Power Zone 5"]  # VO2

        predictions = []
        for row in X:
            hz4 = float(row[i_hz4] or 0)
            hz5 = float(row[i_hz5] or 0)
            kj = float(row[i_kj] or 0)
            mt = float(row[i_mt] or 0)
            pz4 = float(row[i_pz4] or 0)
            pz5 = float(row[i_pz5] or 0)

            # 简单调整
            adjust = 0
            # 阈值训练 (HR Z4 > 1h 涨, < 30min 跌)
            if hz4 > 3600:
                adjust += 3
            elif hz4 < 1800:
                adjust -= 2
            # 高强度过多
            if hz5 > 1800:
                adjust -= 3
            # 训练量 (按时间加权)
            if mt > 0:
                kj_per_hour = kj / (mt / 3600)
                if 800 < kj_per_hour < 1500:  # 合理训练强度
                    adjust += 2
                elif kj_per_hour > 2000:  # 过度
                    adjust -= 2
            # 阈值功率时间
            if pz4 > 3600:
                adjust += 2
            elif pz5 > 3600:  # VO2 过多
                adjust -= 1

            predictions.append(self.base_ftp + adjust)
        return np.array(predictions, dtype=np.float32)
