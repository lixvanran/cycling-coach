# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| V0.6.x  | ✅ Active          |
| V0.5.x  | ⚠️ Security only   |
| < V0.5  | ❌ End of life     |

## Reporting a Vulnerability

If you discover a security vulnerability in Cycling Coach, please report it privately:

**Email**: lixvanran@users.noreply.github.com
**GitHub**: Open a [private security advisory](https://github.com/lixvanran/cycling-coach/security/advisories/new) (preferred)

Please **do not** open a public issue for security vulnerabilities.

### What to include
- Description of the vulnerability
- Reproduction steps
- Impact assessment
- Suggested fix (if any)

### Response time
- Initial response: within 7 days
- Status update: every 14 days until resolved
- Critical fixes: shipped in next patch release

## Scope

In scope:
- Backend API (FastAPI endpoints)
- Frontend (React, Vite build output)
- Desktop app (Electron)
- File upload handling (FIT parsing)

Out of scope:
- User's own data (you own your data, we don't store it)
- Third-party services (OpenRouter, etc.)
- Knowledge base content license violations (see LICENSE, not a security issue)

## Data Privacy

- All training data is stored **locally** (SQLite on the user's device)
- No data is sent to external services except AI coach queries (via OpenRouter)
- No telemetry, no analytics, no tracking
- User has full control over their data (`workspace/cycling_coach.sqlite`)

## Cryptographic Signatures

**当前状态 (V0.7.1)**: ⚠️ **未启用 GPG 签名**

理由:
- 项目以"本地优先"为主, 用户从 GitHub Release 下载 zip 通常信任 GitHub 自身
- GPG 公钥分发 + 签名自动化 (cosign / sigstore) 是后续工作
- 完整方案: cosign + Sigstore Fulcio + Rekor 透明日志

缓解措施:
- 始终从官方 GitHub Release 拉取, 验证 SHA1 (见 release notes)
- 桌面应用 (PyInstaller) 未来用 sigstore-cosign 签名

不要从第三方镜像下载 zip, 避免供应链攻击。
