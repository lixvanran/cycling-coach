# Contributing to Cycling Coach

Thank you for your interest in contributing! 🎉

## ⚠️ Important: Read the License First

This project is **dual-licensed**:

- **Code** (under `cycling_coach/`, `apps/`, `tools/`, `docs/`) → **MIT License** — open to all
- **Knowledge Base** (under `kb_source/`) → **Restricted License** by 潘震(公路车教练) — **DO NOT contribute training encyclopedia content here**

If you want to add training content, please open an issue first to discuss with the maintainer.

## Areas You Can Contribute

### ✅ Code (MIT) — Welcome
- Bug fixes
- New training algorithms (Coggan, Seiler, Friel-style periodization)
- New UI components
- Performance optimizations
- API endpoint additions
- Test coverage
- Documentation (English/Chinese)

### ⚠️ Data (Restricted) — Discuss First
- New mock training profiles
- Sample FIT files
- Test data for cycling scenarios

### ❌ Knowledge Base (Restricted) — Please Do Not
- New training encyclopedia articles
- Modifications to existing `kb_source/markdown/*.md` files
- New attachments in `kb_source/attachments/`

The training encyclopedia is the copyrighted work of 潘震(公路车教练). It is bundled with the project for **local RAG retrieval only**. Contributing to it requires the original author's direct permission.

## Development Setup

```bash
# 1. Clone
git clone https://github.com/lixvanran/cycling-coach.git
cd cycling-coach

# 2. Backend
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate # macOS/Linux
pip install -e .

# 3. Frontend
cd apps/web
npm install
cd ../..

# 4. Run
tools\start.bat          # Windows
./tools/start.sh          # macOS/Linux
```

## Coding Style

### Python
- Python 3.11+ (use `from __future__ import annotations`)
- Type hints preferred
- Docstrings for all public functions (English acceptable, Chinese OK)
- Use `pathlib.Path`, not `os.path`
- Avoid global state; prefer dependency injection

### TypeScript / React
- Functional components with hooks
- TypeScript strict mode
- Tailwind for styling (avoid inline styles for colors)
- Use existing UI components (`MetricCard`, `panel` class, etc.)

## Commit Convention

```
feat: add Pa:HR Decoupling endpoint
fix: handle null HR in trend calculation
docs: update Periodization docs
refactor: extract FTP methods to core/metrics/ftp.py
test: add unit tests for ACWR module
```

## Pull Request Process

1. Fork the repo
2. Create a feature branch (`git checkout -b feat/your-feature`)
3. Make your changes
4. Run tests (when available)
5. Update README/docs if needed
6. Submit PR with clear description

## Reporting Issues

Please use [GitHub Issues](https://github.com/lixvanran/cycling-coach/issues).

Include:
- Reproduction steps
- Expected vs actual behavior
- OS / Python version / Node version
- Sample FIT file (if activity-related) — but be aware of the license terms

## Code of Conduct

Be respectful, helpful, and constructive. We're all here to build something cool for cyclists.

## License Reminder

By contributing code, you agree your contributions are licensed under **MIT**.
By contributing to `kb_source/`, you affirm you have permission from 潘震(公路车教练)
or you have a separate written agreement with the original author.
