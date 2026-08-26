# Cycling Coach 对标 GoldenCheetah 整体优化规划

> 目标：把"训练面板"从"对标 TrainingPeaks 表面"升级到"对标 GoldenCheetah 核心分析能力"
> 立场：开源 · 本地优先 · 中文教练知识库差异化
> 时间：5 个大版本递进，每版独立可交付、可测试

---

## 0. 背景与判断

**GoldenCheetah (v3.7, 20 年迭代)** 是开源骑行分析天花板：
- 核心：Coggan 训练科学体系 (PMC, CP, W'bal, BikeScore)
- 优势：高度可定制、内置公式语言、Python 嵌入、100+ 文件格式
- 短板：UI 老旧 (Qt)、本地文件为主 (无云协作)、学习曲线陡

**我们当前 v0.5.1** 已覆盖 GC 表面 UI，但 **核心分析能力欠缺 60%**：
- ✓ 已有：PMC、CP 曲线、NP、TSS、CTL/ATL/TSB、课程库、训练百科
- ❌ 缺：区间分布、W'bal、CP 3 参数、Compare、Trends 深度化、Periodization、HRV、AeroLab、自定义指标

**结论**：先把 GC 核心分析能力补齐，再说自定义扩展。

---

## 1. 优化路线图 (5 个版本)

| 版本 | 主题 | 核心交付 | 优先级 |
|------|------|---------|--------|
| **v0.6** | P0 - 核心分析能力 | 区间分布 · W'bal · CP 3 参数 · Compare · Trends 深度 | 🔴 必做 |
| **v0.7** | P1 - 训练科学化 | 周期化 · FTP 检测 · RPE · Goal Event · TSB 雷达 | 🟠 重要 |
| **v0.8** | P2 - 高级生理学 | AeroLab · HRV · Decoupling · 多日趋势叠加 | 🟡 增值 |
| **v0.9** | P3 - 课程生态 | ErgDB 集成 · 训练台控制 · 路线库 · 课程社区 | 🟢 差异化 |
| **v1.0** | P4 - 完整专业平台 | Diary · 公式语言 · Python 嵌入 · 教练多用户 | 🟢 旗舰 |

**预计总工作量**：3-4 个月（每周一版本）
**每个版本独立交付**：完成后沙箱 e2e 验证 → 打包 → 用户自测

---

## 2. v0.6 - 核心分析能力 (本次主线)

> 目标：单次活动能看出"专业玩家水准"，多活动能对比出趋势

### 2.1 功率区间分布 (Power Zones)
**当前**：只有 Z1-Z5 4 个区，且只算时长分布
**目标**：完整 7 区 (Coggan) + %FTP 实时区间 + 区间时长直方图 + 区间内平均功率/平均心率/平均踏频

#### 后端 (`cycling_coach/core/metrics/zones.py`)
```python
# 7 区 Coggan 标准
ZONES = {
    "Z1": (0, 55, "主动恢复"),
    "Z2": (56, 75, "耐力基础"),
    "Z3": (76, 90, "节奏"),
    "Z4": (91, 105, "阈值"),
    "Z5": (106, 120, "VO2max"),
    "Z6": (121, 150, "无氧"),
    "Z7": (151, 999, "神经肌肉"),
}
def zone_distribution(activity_id) -> dict:
    # 走 sample_power → time_in_zone → count
    ...
def zone_detail(activity_id) -> list[ZoneSummary]:
    # 每个区: 时长, %占比, 平均功率, 平均心率, 平均踏频
    ...
```

#### API
- `GET /activities/{id}/zones` → 7 区分布
- `GET /activities/{id}/zone-detail` → 每区详细统计

#### 前端 (ActivityDetail 新区块)
- 横向 7 段 bar (与 GC 风格一致)
- 每段 hover 弹出 tooltip: 时长 / % / 平均功率
- 右侧: 7 区表格 (区名 / 区间 / 时长 / 占比 / 平均功率)

### 2.2 W'bal (W 平衡) 模型
**当前**：完全没有
**目标**：基于 (CP, W') 实时计算 W' 余额，绘制活动内 W'bal 曲线

#### 原理
- `W'(t) = W' - ∫max(0, P(t) - CP) dt`
- 当 P < CP 时, W' 以指数恢复
- W' 耗尽 ≈ 比赛结束时刻

#### 后端 (`cycling_coach/core/metrics/wbal.py`)
```python
class WBalCalculator:
    def __init__(self, cp: float, w_prime: float = 20000):
        self.cp = cp
        self.w_prime = w_prime
    def compute(self, power_series: list[float], times: list[float]) -> list[float]:
        ...
    def summary(self) -> dict:
        # 最低余额, 耗尽时间点, 平均利用率
        ...
```

#### API
- `GET /activities/{id}/wbal?cp=250` → W'bal 序列 + 摘要

#### 前端
- ActivityDetail 新增 "W' 平衡" tab
- 折线图 (Recharts) + 关键事件标记 (W' 耗尽、恢复、关键冲刺)
- 摘要卡片: 最低余额 / 耗尽次数 / 建议下次补给

### 2.3 CP 3 参数模型 + 自动检测
**当前**：简单 mean-max 曲线
**目标**：完整 3 参数 (CP, W', Pmax) + 多种曲线叠加 (current/season/all-time)

#### 后端 (`cycling_coach/core/metrics/curve.py` 升级)
```python
@dataclass
class CPM3Result:
    cp: float           # 临界功率 (W)
    w_prime: float      # 无氧储备 (J)
    pmax: float         # 5s 最大功率
    r2: float           # 拟合优度
    confidence: str     # high/medium/low

def fit_cp_3p(activities: list) -> CPM3Result:
    # 使用非线性最小二乘拟合
    # P(t) = W'/t + CP (asymptote) + Pmax * exp(-t/tau)
    ...

def detect_cp_auto(activities: list, lookback_days=90) -> CPM3Result:
    # 自动检测: 取最近 N 天数据, 找最佳窗口
    ...
```

#### API
- `GET /athlete/cp?lookback=90` → CP 3 参数 + 历史曲线
- `POST /athlete/cp/detect` → 触发自动检测

#### 前端 (PowerCurve 页 升级)
- 现有曲线保留, 新增 3 参数拟合曲线 (虚线)
- 时间窗选择: 30/90/180/365/all
- 摘要卡片: CP 数值 / W' 数值 / R² / 置信度

### 2.4 Compare 模式 (活动对比)
**当前**：完全没有
**目标**：选 2-3 个活动并排对比关键指标

#### 后端
- `GET /activities/compare?ids=1,2,3` → 多活动关键指标 JSON
- 公共指标: 时长, 距离, 爬升, NP, IF, TSS, 平均功率, 平均心率, 区间分布, W'bal 摘要, 功率曲线点

#### 前端 (ActivityList 升级)
- 多选 checkbox (上限 3 个)
- 选中后出现 "对比" 按钮 → 进入 Compare 页
- Compare 页布局 (与 GC 类似):
  - 顶部: 3 个活动卡片横排 (时间/标题/关键数值)
  - 中部: 关键指标表格 (左列指标, 右 3 列各活动)
  - 底部: 重叠曲线 (功率曲线 / 心率曲线 / W'bal 曲线)

### 2.5 Trends 深度化
**当前**：只有 PMC 单图 + 最近 7 天 4 卡
**目标**：可配置的多指标趋势图 (与 GC Trends 类似)

#### 后端
- `GET /trends?metric=tss&from=2024-01-01&to=2024-12-31&group=week`
- 支持 metric: tss, np, hr_avg, distance, duration, elevation, rpe
- group: day / week / month
- 返回: 时间序列数组

#### 前端 (Dashboard 加 Trends 区)
- 配置栏: 选指标 + 时间窗 + 分组方式
- 主图: 折线图 (Recharts) + 渐变填充
- 同期对比: 显示去年同期曲线
- 趋势标注: 自动检测峰值/谷值

### 2.6 v0.6 验收标准
- [ ] ActivityDetail 7 区分布 + 每区详情
- [ ] ActivityDetail W'bal 曲线
- [ ] PowerCurve 3 参数拟合 + 时间窗切换
- [ ] Compare 页 2-3 活动对比
- [ ] Dashboard Trends 区域可配置
- [ ] 沙箱 e2e: 3 个测试活动 → 5 个核心 UI 全部正常
- [ ] TypeScript 0 错误
- [ ] 所有版本号统一 v0.6.0
- [ ] 打包 zip (含训练百科) + 用户自测

---

## 3. v0.7 - 训练科学化 (下次)

### 3.1 Periodization 周期化
- 训练周期 (Plan Period) 模型升级: 基础期 → 强化期 → 巅峰期 → 过渡期
- 自动建议当前周训练侧重 (基于当前 CTL/TSB 状态)
- 训练课目标自动匹配: Z2 量大 / Z3-Z4 间歇 / Z5 关键

### 3.2 FTP 检测流程
- 专门的 FTP 测试活动类型 (8/20/60min 分段)
- 测试结果自动应用到全部功率计算
- FTP 历史曲线 (timeline)
- 自动建议: 上次 FTP > 6 周 → 弹窗提醒复测

### 3.3 RPE 主观疲劳
- 每日 RPE 1-10 打卡 (类似 TP "rate this workout")
- 与 TSS 叠加: 客观负荷 vs 主观感受
- 偏离度高 → 标记需要休息

### 3.4 Goal Event 比赛日
- 比赛事件管理: 名称 / 日期 / 距离 / 类型 / 重要度
- 倒计时 + 状态条 (训练 / 减量 / 巅峰)
- TSB 目标自动建议: TT +5~+15 / 单日赛 +10~+20 / 多日赛 +5~+10
- taper 计划: 倒推每周 TSS 减幅

### 3.5 训练状态雷达图
- 5 维评估: 体能 / 疲劳 / 状态 / 节奏 / 恢复
- 雷达图 (Recharts) + 单项分数

---

## 4. v0.8 - 高级生理学

### 4.1 AeroLab (CdA 估算)
- 输入: 体重 / 路面 / 风向 / 速度/功率
- 输出: 估算 CdA 值
- 多次测试比对: 装备 / 姿势 / 骑行服

### 4.2 HRV 追踪
- 每日静息 HR / HRV 录入
- 趋势曲线 + 异常告警
- 与训练负荷叠加分析

### 4.3 Pa:HR Decoupling
- 有氧效率衰减指标
- 长距离 (>2h) 自动计算
- 训练状态: 衰减 < 5% 良好 / >10% 需调整

### 4.4 体能比 / TIF
- 阈值/实际 比值
- 单次 / 长期趋势
- 训练目标达成度

---

## 5. v0.9 - 课程生态 (差异化)

### 5.1 ErgDB 课程导入
- 接入 TrainerDay 公共课程库 (ErgDB 协议)
- 按目标/时长/主导区筛选
- 一键下载到 Builder

### 5.2 智能训练台控制
- ANT+ FE-C 协议模拟
- 课程直接推送到训练台
- 实时功率匹配度监控

### 5.3 路线库
- GPX 导入 + 解析
- 路线图 + 爬升剖面
- 配速建议 (基于 FTP)

### 5.4 课程社区
- 课程评价 / 收藏 / 分享
- 浏览他人公开课程
- (本地版, 不依赖云)

---

## 6. v1.0 - 完整专业平台 (旗舰)

### 6.1 训练日记 (Diary)
- 富文本 (Tiptap/Lexical)
- 图片 / 心情 / 天气
- 按日/周/月聚合

### 6.2 自定义指标公式
- 类 Excel 公式语言
- 内置函数: avg, max, min, np, tss, riegel, trimp
- 用户上传指标到社区

### 6.3 Python 嵌入图表
- 内嵌 Python 运行时
- 用户写脚本生成自定义图
- matplotlib / plotly 输出

### 6.4 教练多用户模式
- 一账号管多运动员
- 教练视角 / 运动员视角切换
- 共享训练计划 / 报告

---

## 7. 推荐执行顺序

**我的建议：从 v0.6 开始，按 P0→P5 顺序**

原因：
1. **P0 是专业度最关键差异化**：区间分布 + W'bal + CP 3 参数 + Compare + Trends，这 5 块做完, 我们从"模仿 TP" 跃升到"对标 GC 核心"
2. **P0 全部基于已有数据**：不需要新数据源, 已有 FIT 解析 + sample_power 即可
3. **P0 1 个月可完成**：每个模块 ≤ 1 周
4. **用户能立刻感受到升级**：从"看数"到"懂数"

**如果你有不同优先级**（比如更想要 P1 的训练科学化，或 P3 的训练台控制），告诉我，我重新排。

---

## 8. v0.6 详细任务拆解 (本次可执行)

### 8.1 后端 (Python)
| 文件 | 内容 | 工时 |
|------|------|------|
| `core/metrics/zones.py` | 7 区 Coggan 计算 + 区间详情 | 0.5d |
| `core/metrics/wbal.py` | W'bal 计算 + 摘要 | 1d |
| `core/metrics/curve.py` | 3 参数 CP 拟合 (升级) | 1d |
| `api/routers/trends.py` | 趋势 API (新) | 0.5d |
| `api/routers/activities.py` | 加 zones/wbal/compare 端点 | 0.5d |
| 测试 | 单元 + 集成 | 1d |

### 8.2 前端 (React)
| 文件 | 内容 | 工时 |
|------|------|------|
| `pages/ActivityDetail.tsx` | 加 Zones / W'bal tab | 1d |
| `pages/ActivityList.tsx` | 加多选 + 对比按钮 | 0.5d |
| `pages/ComparePage.tsx` | (新) 3 活动对比 | 1d |
| `components/PowerCurve.tsx` | 加 3 参数曲线 | 0.5d |
| `components/Trends.tsx` | (新) 可配置趋势 | 1d |
| `lib/api.ts` | 加新端点 | 0.5d |
| 视觉细节 | 与 v0.5.1 一致 | 0.5d |

### 8.3 测试 + 打包
| 内容 | 工时 |
|------|------|
| 沙箱 e2e (5 场景) | 1d |
| TypeScript + Build | 0.5d |
| 打包 + 用户自测 | 0.5d |

**总计**：约 8-10 天 (按每日 8h)

---

## 9. 风险与依赖

**风险**：
- W'bal 计算准确性依赖 (CP, W') 准确 → 需要先确保 CP 估计算法 OK
- Compare 模式大量数据点渲染 → 需要 sample 抽样
- 3 参数 CP 拟合 → 数据不足时 R² 低，需 fallback

**依赖**：
- 现有 sample_power 表 (每个活动秒级功率)
- 现有 athlete 表 (FTP)
- 现有 activity 表
- Recharts 库 (已在)

**不依赖**：
- 不需要新数据源
- 不需要新外部 API
- 不需要新依赖

---

## 10. 决策点（需要你确认）

1. **起点**：v0.6 还是其他？ (建议 v0.6)
2. **v0.6 范围**：5 个模块全做 还是 先做 2-3 个？(建议全做)
3. **CP/W' 默认值**：CP 未知时默认 250W？W' 默认 20000J？ (建议从 athlete 表读)
4. **Trends 默认指标**：TSS/CTL/ATL/TSB？ (建议默认 4 个都能切换)
5. **打包策略**：v0.6 含训练百科 (149MB) 还是 纯代码？ (建议含)
