# Cycling Coach V0.7.5.1 - 用户体验修复

> **发布日期**: 2026-08-31
> **包大小**: ~155MB (含 kb_source/)
> **解压即可用**: `tools\\start.bat` (Win) / `./tools/start.sh` (Unix)

## V0.7.5.1 vs V0.7.5

### 1. KB 侧栏直达 (修复用户反馈)
**问题**: 之前"知识库"页面只显示一个根目录入口, 8 个顶级分类需要再点一层才能进.

**修**:
- [x] **主侧栏 KB hover 二级菜单** — 鼠标悬停"知识库"自动弹出 8 个顶级分类, 点击直达
- [x] **store 持久化 selectedKbCategory** — 跨页面切换保持选中分类
- [x] **kb-category 路由** — 主侧栏直接进具体分类

### 2. AI 引用精准 (修复"牛头不对马嘴")
**问题**: mock 模式下, AI 报告直接堆砌 KB chunk 全文, 引用内容跟用户问题无关.

**修**:
- [x] **analyze_activity.py 改 query** — V0.7.4.1 用文件名+数字当 query (导致检索错乱), 改为训练学主题词 (focus + 活动类型 + athlete 参数)
- [x] **相邻 chunk 上下文** — 主 chunk 拼前/后 1 个 chunk, 提升引用完整性
- [x] **_format_kb_answer 抽句** — 按用户问题关键词从 KB chunk 抽取 top-5 相关句子 (单字+2-gram 加权), 不再堆砌全文
- [x] **retrieved 按相关性重排** — 不再按 FTS rank 死排序, 计算用户关键词命中数, 真正的"相关"

### 3. 空页面修复
**问题**: Sidebar 有 Insights / Phases / FTP Test 入口, 但 App.tsx 路由没接, 点进去是空白.

**修**:
- [x] **App.tsx 路由** — 加 `{view === "phases" && <PhasesPage />}` / `insights` / `ftp-test`

## 沙箱验证
- TSC: **0 错**
- pytest: **41 passed** (无回归)
- Vite build: **1.21MB JS / 76KB CSS** (gzip 337KB / 17KB)
- 后端冒烟: 105 method, **0 个 5xx**

## 端点
- V0.7.5: 93 paths / 105 method
- V0.7.5.1: 93 paths / 105 method (无变化, 主要前端 + AI 体验)

## 没 commit / 没 push
按用户规则, 修改留在 working tree, 等显式 push 同意.
