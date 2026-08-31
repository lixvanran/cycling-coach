# Cycling Coach V0.7.5.5 - 依赖锁版本 + Toast 替换 alert

> **发布日期**: 2026-08-31

## V0.7.5.5 vs V0.7.5.4

### DEV-18 依赖管理
- [x] `pyproject.toml` 关键包加 `<1.0` / `<2.0` / `<3.0` 上限 (fastapi, pydantic, sqlalchemy, numpy, openai, httpx)
- [x] `requirements.txt` 跟 pyproject 同步 (缺 reportlab, fit-tool, pytest-asyncio 已补)
- [x] 注释加注释说明"实际项目用 pyproject.toml"

### UX-3 toast 替换 alert (前端体验)
- [x] 新建 `components/Toast.tsx` — 全局 toast 系统, 4 种 (success/error/warn/info), 右上角浮层, 3.5s 自动消失
- [x] `App.tsx` 挂载 `<ToastContainer />`
- [x] 6 个页面替换 alert: ImportPage / Profile / ActivityDetail / CalendarPage / DiaryPage / FTPTestPage
- 用户不再被阻塞 alert 打断, 错误信息自动消失

## 沙箱验证
- TSC: **0 错**
- pytest: **41 passed**
- Vite build: 1.219MB JS / 77KB CSS (gzip 339KB / 17KB)
- 业务端点 11/11 全 200

## 端点
- 93 paths / 105 method (无变化)
