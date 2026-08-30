# Cycling Coach V0.7.4 - 算法严格化 + 同步预留

> **发布日期**: 2026-08-28
> **包大小**: ~162MB (含 kb_source/)
> **解压即可用**: `tools\\start.bat` (Win) / `./tools/start.sh` (Unix)

## V0.7.4 vs V0.7.3

### 算法严格化 (P0)
- [x] W'bal 升级 Skiba 2012 strict differential (从简化模型到真 differential)
- [x] 新增 7 个物理性测试 (idle / constant CP / depletes / oscillation / recovery curve / no-negative / not-exceed)
- [x] 全部核心算法审查, 引用学术标准 (Coggan 2003 / Skiba 2012 / Gabbett 2016 / Plews 2013 / Friel / Seiler 2010)

### Strava 同步接口预留 (P1)
- [x] 6 个端点: /api/sync/providers + /strava/{auth,callback,status,activities,sync,disconnect}
- [x] core/sync/base.py + strava.py Provider abstract class
- 当前全部 501 (V0.8+ 实装, 需 STRAVA_CLIENT_ID/SECRET)

### 课程导出第 5 格式 (P1)
- [x] FIT Workout (Garmin Edge / Wahoo ELEMNT 通用)
- 5 格式全跑通: ZWO / MRC / ERG / FIT / JSON

### 架构整理 (P2)
- [x] docs/ARCHITECTURE.md 完整重写, 反映 V0.7.4 真实结构
- [x] tests/ 强制包含 (用户能跑测试, 不依赖 git)

## 沙箱验证 (V0.7.4 端到端)
- TSC: 0 错
- pytest: **41 passed** (14 metrics + 13 power + 4 acwr + 3 ftp + 7 wbal-skiba)
- Vite build: 1.119MB (gzip 311KB)
- 后端冒烟: 15 端点 200/501 正确
- 课程导出: 5 格式跑通

## 端点
- V0.7.3: 81 / V0.7.4: **88 端点 / 100 method** (+7 sync)

## 没 commit / 没 push
按用户规则, 修改留在 working tree, 等显式 push 同意.
