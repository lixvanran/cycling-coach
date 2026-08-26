# GitHub Push Instructions / GitHub 推送说明

本仓库已分阶段提交完成 (15 个 commit), 但沙箱无网络, **需在本机 push 到 GitHub**。

This repository has been committed in stages (15 commits), but the sandbox has no network.
**You need to push to GitHub from your local machine.**

## Steps / 步骤

### 1. 在本机拉取最新代码 / Pull latest code
```bash
cd cycling-coach
git pull   # 如果有远程的话
```

### 2. 创建 GitHub 仓库 / Create GitHub repository
访问 https://github.com/new, 仓库名: `cycling-coach`, **不要**初始化 README/.gitignore/license
Visit https://github.com/new, repo name: `cycling-coach`, **do not** initialize README/.gitignore/license

### 3. 关联远程仓库 / Add remote
```bash
git remote add origin https://github.com/lixvanran/cycling-coach.git
git branch -M main
```

### 4. 推送 / Push
```bash
git push -u origin main
```

如果 push 卡住或太大 (知识库 markdown ~1.7MB 应该没问题), 用:
```bash
GIT_TRACE=1 git push -u origin main --verbose
```

### 5. 验证 / Verify
访问 https://github.com/lixvanran/cycling-coach, 检查:
- ✅ LICENSE 文件 (英文 MIT)
- ✅ LICENSE.zh-CN 文件 (中文 MIT)
- ✅ kb_source/LICENSE 文件 (受限协议)
- ✅ README 显示双协议 + badge
- ✅ 15 个 commit 历史

### 6. 设置 GitHub repository description / Configure repo
Settings → General:
- Description: `公路自行车 AI 教练 · Road cycling AI coach (MIT + Restricted KB)`
- Website: (留空)
- Topics: `cycling`, `ai-coach`, `fastapi`, `react`, `power-meter`, `training-load`, `rag`, `openai-compatible`, `mit-license`

Settings → Features:
- ✅ Issues
- ✅ Pull Requests
- ❌ Wiki (暂时)
- ✅ Discussions (可选)

### 7. 准备 Release / Prepare V0.6.1 release
```bash
git tag -a v0.6.1 -m "V0.6.1: GC Differentiation + UX Depth"
git push origin v0.6.1
```

然后在 GitHub 上:
- 访问 https://github.com/lixvanran/cycling-coach/releases/new
- Tag: v0.6.1
- Title: V0.6.1 — GoldenCheetah Differentiation
- Description: 复制 CHANGELOG.md 的 V0.6.1 段
- 附件: 上传 `cycling-coach-v0.6-source.zip` + `cycling-coach-v0.6-kb.zip`

## 注意事项 / Notes

### KB 拆分推送
- `kb_source/markdown/` (~1.7MB) → Git 跟踪
- `kb_source/attachments/` (165MB) → **不在** Git 里, 通过 Release 单独下载 `cycling-coach-v0.6-kb.zip`
- `apps/desktop/build/` → 不在 Git 里 (electron-builder 用)

### 已 commit 但**可能**不想 push 的内容
- `apps/desktop/` (闪退代码, 标记为 code reserved)
- 如果你想清空, 删 commit 然后只保留核心代码

### 协议保护 / License protection
- `kb_source/markdown/` 中的内容受 `kb_source/LICENSE` 保护
- 即使被 fork, 也不可再分发 / 商用
- 这是技术 + 法律双层保护

### 提交签名 (可选) / Commit signing (optional)
```bash
gpg --gen-key  # 第一次
git config --global user.signingkey <key-id>
git config --global commit.gpgsign true
```

然后在 GitHub Settings → SSH and GPG keys → New GPG key 添加公钥。
