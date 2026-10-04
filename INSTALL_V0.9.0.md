# Cycling Coach V0.9.0 安装指南

> **V0.9.0 重大更新**: Inbox folder watcher — Garmin/FIT 自动同步 (TP 替代品核心闭环)
> **新增依赖**: `watchdog>=4.0,<7.0`
> **新 CLI 命令**: `python -m cycling_coach folder-watch {start|stop|status|once|install}`
> **新文件**: 1 个 module + 1 个 CLI + 1 个测试文件

## V0.9.0 新功能: Inbox Watcher

**这是把 cycling-coach 推向 "TP 替代品" 的关键一步。**

### 解决的问题

TP / WKO / GoldenCheetah 用户每天从码表 (Garmin/Wahoo/Zwift) 导出 FIT 文件后, 要手动拖到 web 上传 — 烦。

现在: 丢进 inbox 文件夹 → 自动解析 → 自动入库。

### 用法 (5 步上手)

#### 1. 找你的 inbox 目录

```bash
python -m cycling_coach folder-watch status
# 输出:
#   inbox dir:  /Users/you/Library/Application Support/cycling-coach/inbox
#   state:      STOPPED
```

平台默认位置:
- **macOS**:   `~/Library/Application Support/cycling-coach/inbox`
- **Linux**:   `${XDG_DATA_HOME:-~/.local/share}/cycling-coach/inbox`
- **Windows**: `%APPDATA%\cycling-coach\inbox`

#### 2. (可选) 自定义目录

环境变量覆盖:
```bash
export CYCLING_COACH_INBOX=~/Documents/cycling-inbox
python -m cycling_coach folder-watch status
```

#### 3. 配置你的码表 (Garmin Connect / Wahoo / Zwift)

Garmin Connect 网页 → 右上头像 → Settings → Privacy & Data → "Export Original" → 选 FIT → 下载到 inbox 文件夹
Wahoo ELEMNT: 设置 → 自动同步到 Dropbox → Dropbox 文件夹软链到 inbox
Zwift: Zwift 导出 → Activities → 选 FIT → 丢进 inbox

#### 4. 启动 watcher

```bash
# 前台模式 (调试用)
python -m cycling_coach folder-watch start

# 后台模式
python -m cycling_coach folder-watch start --daemon
```

#### 5. 验证

```bash
python -m cycling_coach folder-watch status
#  state:    RUNNING (PID 12345)
#  processed: 3 个文件

# 跑一次扫描 (调试 / cron 用, 不需要 daemon)
python -m cycling_coach folder-watch once
#  处理完成: 1 个新文件入库

# 停掉
python -m cycling_coach folder-watch stop
```

### 服务化 (开机自启)

#### macOS (launchd)

1. 复制 plist 到 `~/Library/LaunchAgents/`:
```bash
cp tools/com.lixvanran.cycling-coach.inbox.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.lixvanran.cycling-coach.inbox.plist
```

2. plist 内容 (示例):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.lixvanran.cycling-coach.inbox</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>-m</string>
    <string>cycling_coach</string>
    <string>folder-watch</string>
    <string>start</string>
  </array>
  <key>WorkingDirectory</key><string>/path/to/cycling-coach</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict>
</plist>
```

#### Linux (systemd --user)

`~/.config/systemd/user/cycling-coach-inbox.service`:
```ini
[Unit]
Description=Cycling Coach Inbox Watcher

[Service]
WorkingDirectory=/path/to/cycling-coach
ExecStart=/usr/bin/python3 -m cycling_coach folder-watch start
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

启用:
```bash
systemctl --user daemon-reload
systemctl --user enable cycling-coach-inbox.service
systemctl --user start cycling-coach-inbox.service
```

#### Windows (Task Scheduler)

1. Task Scheduler → Create Task
2. Triggers: At startup
3. Actions: Start a program
   - Program: `python`
   - Arguments: `-m cycling_coach folder-watch start`
   - Start in: `C:\path\to\cycling-coach`

### 工作原理

```
FIT 丢进 inbox
  ↓
watchdog 监听 created/moved/modified
  ↓
等待文件大小稳定 N 次 (避免读到正在写入)
  ↓
计算 sha256
  ↓
检查注册表 (processed.json) → 已处理跳过
  ↓
调 ActivityService.upload() → 解析 → 入库 → 计算指标
  ↓
写入注册表 → 不再重复处理
```

**关键安全机制**:
- **Dedup**: sha256 哈希 — 同一个 FIT 多次丢进不会被重复入库
- **Stable**: 文件大小稳定后才处理 — 避免读到正在写入的文件
- **Extension whitelist**: 只接受 `.fit`/`.tcx`/`.csv`
- **Size limit**: 默认 50 MB, 防止异常
- **PID 锁**: 防止多实例并发跑
- **Graceful shutdown**: SIGTERM 等当前文件处理完再退

### 配置文件 (.env)

可调参数 (全部有默认值, 通常不用改):
```bash
# inbox_enabled=True  # False = 关闭 (不影响其他功能)
# inbox_dir=""        # 空 = 自动按平台推导
# inbox_debounce_seconds=2.0  # 文件大小稳定后多久处理
# inbox_stable_polls=3        # 连续 N 次大小不变才算"写完"
# inbox_poll_interval_ms=200  # 大小检查间隔 (ms)
# inbox_max_file_mb=50        # 大于此 MB 跳过
# inbox_extensions=".fit,.tcx,.csv"
```

### 故障排除

| 症状 | 原因 | 解决 |
|------|------|------|
| `state: STOPPED` 但 daemon 应在跑 | 进程死了 / PID 文件陈旧 | 看 log 文件; `stop` 后重启 |
| `no such table: athletes` | DB 没初始化 | watcher 启动会自动 init_db, 检查 `.env` 的 `workspace_dir` 是否可写 |
| 文件处理了 2 次 | dedup 没工作 | 看 `processed.json`, 手动清理 |
| 文件 size 一直变 | 写入方多次 reopen | 调大 `inbox_debounce_seconds` 或 `inbox_stable_polls` |
| 不支持的文件被忽略 | 扩展名白名单 | 看 `.env` 的 `inbox_extensions` |

### 与其他功能的交互

| 功能 | 影响 |
|------|------|
| Web 上传 (`POST /api/activities/upload`) | ✅ 同时工作 (不同 code path) |
| Strava 同步 | ✅ 互补 (Strava 走 webhook, watcher 走文件) |
| AI 报告生成 | ✅ 自动触发 (ActivityService.upload 已接 background_tasks) |
| Dashboard / Trends / Compliance | ✅ 数据自动可用 |

### 升级

从 V0.8.x 升 V0.9.0:

```cmd
cd cycling-coach
git pull origin main
tools\stop.bat          # 停掉后端
pip install -e ".[all]" # 装新依赖 (watchdog)
tools\start.bat         # 重启后端 (新功能自动可用)
```

老用户不需要迁移 (新功能不影响现有数据)。

## git clone 用户必读 ⚠️

`cycling_coach/static/`（前端 build 产物）在 `.gitignore` 里——它是构建输出，
不进版本库。所以 **git clone 出来的源码第一次没有前端产物**。

V0.9.0 起，`tools\start.bat` 会**自动检测并 build 一次**（需要 Node + pnpm，
约 1-2 分钟），之后每次启动都命中缓存、不再需要。

- **正式用户请用官方 zip 包**：它自带前端产物，**完全不需要 Node**。
- **开发者 git clone**：直接双击 `tools\start.bat` 即可，脚本会提示并自动 build。
  如果没装 Node/pnpm，它会明确告诉你，并建议改用 zip 包。
