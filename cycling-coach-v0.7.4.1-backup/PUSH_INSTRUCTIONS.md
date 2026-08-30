# GitHub 推送指南 / GitHub Push Guide

> **沙箱无网络**, 仓库已分阶段提交 (16 commits + tag v0.6.1),
> 需在本机完成 GitHub push + Release。

> **Sandbox has no network.** Repository has been committed in 16 stages + tag v0.6.1.
> You need to push to GitHub + create the release from your local machine.

---

## ✅ 已完成 (Sandbox-side)

- [x] **16 个 commit** 按特性分阶段提交
  - License setup · RPE · 海拔 · Decoupling · ACWR · GPS · FTP · Periodization · Analytics · Desktop · UX · API · UI · AI
- [x] **Tag**: `v0.6.1` (GoldenCheetah Differentiation + UX Depth)
- [x] **543 files** tracked
- [x] **Dual license**: MIT (code) + Restricted (kb_source/ by 潘震)
- [x] **Bilingual docs**: LICENSE.zh-CN + CONTRIBUTING.md (中英)
- [x] **.gitignore** 完善: workspace, .venv, node_modules, kb_source/attachments/ (165MB)
- [x] **Issue/PR templates** + **CHANGELOG** + **ROADMAP**

## 📋 待你完成 (Local-side)

### 1. 在本机拉取最新代码
```bash
# 假设你的项目目录是 cycling-coach/
cd cycling-coach
git status  # 应该干净, 16 个 commit 都已提交
```

### 2. 创建 GitHub 仓库
访问 https://github.com/new
- **Repository name**: `cycling-coach`
- **Description**: `公路自行车 AI 教练 · Road cycling AI coach (MIT + Restricted KB)`
- **Public** (推荐, 开源)
- ⚠️ **不要**勾选 Add README / .gitignore / license (我们已自己写好了)

### 3. 关联 + 推送
```bash
git remote add origin https://github.com/lixvanran/cycling-coach.git
git branch -M main
git push -u origin main
git push origin v0.6.1
```

如果 push 失败 (大文件 / 网络):
```bash
# 看哪个文件太大
git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' | awk '/^blob/ {print $3, $4}' | sort -n -r | head -10

# 知识库 markdown 1.7MB 不大, 应该能 push
# 如果真的卡, 考虑 Git LFS (但 KB markdown 是文本, 没必要 LFS)
```

### 4. 创建 GitHub Release
访问 https://github.com/lixvanran/cycling-coach/releases/new

- **Choose a tag**: `v0.6.1` (刚才 push 的)
- **Release title**: `V0.6.1 — GoldenCheetah Differentiation + UX Depth`
- **Description**: 复制 [CHANGELOG.md](CHANGELOG.md) 的 V0.6.1 段
- **Attach binaries** (拖入):
  - `cycling-coach-v0.6-source.zip` (1.5MB) — 源码 (不含 KB)
  - `cycling-coach-v0.6-kb.zip` (155.9MB) — 知识库 (训练百科 + 252 附件)
- **Set as latest release**: ✅
- **Create release**

### 5. 配置仓库 (Settings)

**General**:
- Description: 公路自行车 AI 教练 · Road cycling AI coach (MIT + Restricted KB)
- Website: (留空, 等有了再加)
- Topics (标签): `cycling`, `ai-coach`, `fastapi`, `react`, `power-meter`, `training-load`, `rag`, `openai-compatible`, `mit-license`

**Features**:
- ✅ Issues
- ✅ Pull Requests
- ❌ Wiki (暂时)
- ✅ Discussions (可选, 让用户讨论训练方法)

### 6. 添加 Topics 跟 About (仓库主页右上角齿轮)

## 🔒 License 保护检查清单

| 检查 | 状态 |
|------|------|
| `LICENSE` 英文 MIT | ✅ 1.9KB |
| `LICENSE.zh-CN` 中文 MIT | ✅ 1.6KB |
| `kb_source/LICENSE` 中英双语受限 | ✅ 5.9KB |
| `kb_source/NOTICE` 作者署名 | ✅ 3.8KB |
| `NOTICE` 整体项目说明 | ✅ 2.3KB |
| `CONTRIBUTING.md` 双协议贡献说明 | ✅ 3.3KB |
| `README.md` 双协议 + GitHub badge | ✅ 18KB |
| `CHANGELOG.md` 版本历史 | ✅ 3.1KB |
| `kb_source/markdown/` 受限 (1.7MB) | ✅ |
| `kb_source/attachments/` 不在 git (165MB) | ✅ 走单独 zip |

## 📊 推送统计

| 项 | 数 |
|----|---|
| Commits | 16 |
| Files tracked | 543 |
| Code lines | ~25,000 |
| Branches | main (only) |
| Tags | v0.6.1 |
| Releases | 1 (待创建) |
| Source zip | 1.5MB (152 files) |
| KB zip | 155.9MB (611 files, not in git) |
| Languages | Python 56%, TypeScript 30%, CSS 4%, Other 10% |

## 🤝 后续 (可选)

- 启用 GitHub Pages 部署 Vite build 静态版
- 配置 CI (GitHub Actions) 跑测试
- 设置 Issue labels (bug, enhancement, docs, kb, question)
- 添加 Code of Conduct (如果有协作者)
- 配置 Dependabot (自动更新依赖)

## ❓ 常见问题

**Q: 知识库 markdown 1.7MB 不会太大吗?**
A: Git 单文件 ≤ 100MB 没问题, 1.7MB 远低于。KB attachments 165MB 不在 git, 走 release zip。

**Q: 桌面应用 (apps/desktop/) 闪退, 要不要推?**
A: 推, 但 README 标 V0.5.3 起搁置, dev 模式 (`tools/start.bat`) 是当前方案。

**Q: V0.7 自动周报 PDF 要不要现在做?**
A: 看精力, 推完这次 GitHub 后可以继续。

**Q: 知识库 license 真的能保护吗?**
A: 法律 + 技术双层:
- 法律: `kb_source/LICENSE` 明确禁止再分发 / 衍生 / 商用 / 冒名
- 技术: git fork 也会带 LICENSE, GitHub 检测到 LICENSE 不一致会提示
- 实际: 即使被恶意 fork, 知识库 markdown 体积不大, 维权成本高 → 主要靠"君子协议"+ 协议声明
