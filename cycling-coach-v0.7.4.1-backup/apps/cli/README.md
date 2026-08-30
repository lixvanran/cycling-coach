# Cycling Coach CLI

> 状态:**占位** — V0.3+ 启动

## 用例

- 批量导入 FIT 文件
- CI/CD 跑指标回归测试
- AI 模型评测(benchmark)
- 数据导出 / 备份
- 设备码表离线分析

## 设计

```bash
$ cycling-coach fit analyze *.fit
# 解析 FIT,输出 NP / IF / TSS 等指标

$ cycling-coach fit analyze --athlete=me --json *.fit > report.json
# 输出 JSON 供脚本处理

$ cycling-coach ai report 42 --focus="今天累不累"
# 触发 AI 报告生成,直接输出

$ cycling-coach benchmark --model=m3,m2.7,claude-haiku
# 跑 prompt 评测,对比响应质量
```

## 何时启动

V0.3(有了 AI 基础 + 指标稳定后)。
