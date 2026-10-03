#!/usr/bin/env python3
"""Cycling Coach 自检工具 (Windows 交付路径专用)

## V0.9.0 重写的原因

旧版 diagnose.py 整份都在检查 node / npm / pnpm / esbuild / vite。
但 V0.9.0 起 **Windows 用户的默认路径是不需要 Node 的** ——
`tools/start.bat` 默认 `--desktop`, 后端直接 serve `cycling_coach/static`。

也就是说: 用户遇到问题跑自检, 工具报了一堆"Node 正常"的信息,
而真正让他打不开的东西(静态资源、数据库、数据目录、端口)一个都没查。
诊断工具在诊断错误的东西, 比没有诊断更糟。

## 现在查什么

按"用户会先撞上的顺序"排:

    1. Python / .venv / 关键依赖     —— 装得上吗
    2. 前端静态资源                   —— 打不打得开界面 (V0.9.0 修过的 P0)
    3. 数据目录                       —— 你的训练数据到底在哪、能不能写
    4. 数据库                         —— 能不能开、迁移能不能过、数据在不在
    5. 端口                           —— 被谁占了
    6. 后端能否真正起来               —— 进程内起 TestClient 打 /api/health
    7. 最近的错误日志

第 6 项是这里最有价值的: 它不是"看日志猜", 而是**当场把整个应用起起来打一次
健康检查**。Windows 上跑这一条, 基本就能分辨是"环境没装好"还是"代码炸了"。

## 用法

    tools\\diagnose.bat          (Windows, 推荐)
    python tools/diagnose.py     (任意平台)

退出码: 0 = 没有 FAIL 项; 1 = 有 FAIL。报告写到 workspace/.logs/selfcheck.txt
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()

# 关键: 直接 `python tools\diagnose.py` 运行时, sys.path[0] 是 tools\ 而不是项目根,
# `import cycling_coach` 必然 ModuleNotFoundError。
# start.py 用 venv 里的绝对路径调用所以没暴露, 但用户手敲 python tools\diagnose.py
# 就会撞上 —— 而他撞上这个的时候, 恰恰是他最需要诊断的时刻。
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 与 tools/start.py 保持一致的唯一真相来源
STATIC_CANDIDATES = [
    ROOT / "cycling_coach" / "static",
    ROOT / "apps" / "web" / "dist",
]

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"

_lines: list[str] = []
_results: list[tuple[str, str, str]] = []


def emit() -> None:
    print("\n".join(_lines))


def check(name: str, status: str, detail: str = "") -> None:
    _results.append((name, status, detail))
    icon = {PASS: "[OK]  ", WARN: "[!]   ", FAIL: "[FAIL]"}.get(status, "[?]   ")
    _lines.append(f"{icon} {name}" + (f"\n         {detail}" if detail else ""))


def section(title: str) -> None:
    _lines.append("")
    _lines.append(f"--- {title} " + "-" * max(0, 52 - len(title)))


def data_dir() -> Path:
    """用户数据目录 —— 与 start.py resolve_data_dir 保持一致"""
    return Path.home() / ".cycling-coach" / "workspace"


# ====================================================================== 1
def check_python() -> None:
    section("1. Python 环境")
    v = ".".join(str(x) for x in sys.version_info[:3])
    if sys.version_info < (3, 11):
        check("Python 版本", FAIL, f"{v} — 需要 3.11 或更高")
    else:
        check("Python 版本", PASS, v)

    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    check("虚拟环境", PASS if in_venv else WARN,
          sys.prefix if in_venv else "不在 venv 内 (如果你是用 start.bat 启动的, 这不正常)")

    missing = []
    for mod, why in [("fastapi", "后端"), ("sqlalchemy", "数据库"), ("fitparse", "FIT 解析"),
                     ("pandas", "指标计算"), ("uvicorn", "服务器"), ("pydantic_settings", "配置")]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(f"{mod} ({why})")
    if missing:
        check("关键依赖", FAIL, "缺: " + ", ".join(missing) + "  → 跑 tools\\start.bat 自动装, 或 pip install -r requirements.txt")
    else:
        check("关键依赖", PASS, "fastapi / sqlalchemy / fitparse / pandas / uvicorn 均可导入")


# ====================================================================== 2
def check_frontend() -> None:
    section("2. 前端静态资源 (打不打得开界面)")
    found = None
    for c in STATIC_CANDIDATES:
        _lines.append(f"         查找: {c}")
        if (c / "index.html").exists() and found is None:
            found = c
    if found is None:
        check("前端 build 产物", FAIL,
              "全部候选目录都没有 index.html。桌面模式打不开界面。\n"
              "         修: cd apps/web && npx vite build   (产物落在 cycling_coach/static)")
        return
    n = len(list(found.rglob("*.js")))
    check("前端 build 产物", PASS, f"{found}  ({n} 个 js)")
    # index.html 里的资源引用要真的存在, 否则页面打开是白屏
    html = (found / "index.html").read_text(encoding="utf-8", errors="ignore")
    import re
    refs = re.findall(r'(?:src|href)="\.?/?(assets/[^"]+)"', html)
    broken = [r for r in refs if not (found / r).exists()]
    if broken:
        check("前端资源引用", FAIL, f"index.html 引用了不存在的文件: {broken[:3]} — 页面会白屏")
    elif refs:
        check("前端资源引用", PASS, f"{len(refs)} 个引用全部存在")
    else:
        check("前端资源引用", WARN, "index.html 里没解析到 assets 引用, 请人工确认页面能打开")


# ====================================================================== 3
def check_datadir() -> None:
    section("3. 用户数据目录 (你的训练数据在哪)")
    d = data_dir()
    check("数据目录位置", PASS, str(d))
    if d.exists():
        try:
            probe = d / ".write-probe"
            probe.write_text("x", encoding="utf-8")
            probe.unlink()
            check("数据目录可写", PASS, "可写")
        except Exception as e:
            check("数据目录可写", FAIL,
                  f"不可写: {e}\n         多半是杀软/权限问题。检查该目录权限, 或用 --port 之外的方式换个数据目录")
    else:
        check("数据目录存在", WARN, f"尚未创建, 首次启动会自动建: {d}")

    # 旧路径残留: 旧版 start.py/uninstall.bat 说的是 workspace\, 实际数据在用户目录
    legacy = ROOT / "workspace" / "cycling_coach.sqlite"
    if legacy.exists():
        check("发现旧数据路径", WARN,
              f"{legacy} 也存在数据库。V0.9.0 起真实数据在 {d}, "
              f"旧这个可能只是空壳 —— 确认一下里面的训练记录是不是你要的")


# ====================================================================== 4
def check_database() -> None:
    section("4. 数据库")
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    os.environ["WORKSPACE_DIR"] = str(d)
    try:
        from cycling_coach.data.sqlite import database as D
    except Exception as e:
        check("数据库模块导入", FAIL, f"{type(e).__name__}: {e}")
        return

    try:
        D.init_db()
        check("建表 + 迁移", PASS, "成功")
    except Exception as e:
        check("建表 + 迁移", FAIL, f"{type(e).__name__}: {e}")
        return

    baks = sorted((d / "db_backups").glob("pre-migrate-*.sqlite*"), reverse=True) \
        if (d / "db_backups").exists() else []
    if baks:
        check("迁移前备份", PASS, f"{baks[0].name} (共 {len(baks)} 份)")

    try:
        db = D.SessionLocal()
        n = db.execute(D.text("SELECT COUNT(*) FROM activities")).scalar() or 0
        na = db.execute(D.text("SELECT COUNT(*) FROM athletes")).scalar() or 0
        db.close()
        check("数据可读", PASS, f"{na} 个运动员, {n} 条训练记录")
        if n == 0:
            check("训练数据", WARN, "库里还没有训练记录 —— 首次使用请到「数据 → 导入」上传 FIT")
    except Exception as e:
        check("数据可读", FAIL, f"{type(e).__name__}: {e}")


# ====================================================================== 5
def check_ports() -> None:
    section("5. 端口")
    for port in (8765, 1420):
        pid = None
        try:
            if platform.system() == "Windows":
                out = subprocess.run(["netstat", "-ano"], capture_output=True,
                                     text=True, timeout=10).stdout
                for line in out.splitlines():
                    p = line.split()
                    if len(p) >= 5 and p[0].upper() == "TCP" and p[-2].upper() == "LISTENING" \
                       and p[1].rsplit(":", 1)[-1] == str(port):
                        pid = p[-1]
                        break
            else:
                r = subprocess.run(["lsof", "-ti", f":{port}", "-sTCP:LISTEN"],
                                   capture_output=True, text=True, timeout=10)
                got = r.stdout.strip().splitlines()
                pid = got[0].strip() if got else None
        except Exception as e:
            check(f"端口 {port}", WARN, f"检查失败: {e}")
            continue
        if pid is None:
            check(f"端口 {port}", PASS, "空闲")
        else:
            check(f"端口 {port}", WARN,
                  f"被 PID {pid} 占用。\n"
                  f"         如果那是你自己开的别的程序, 用 --no-kill 启动就不会动它:\n"
                  f"           python tools\\start.py --desktop --no-kill\n"
                  f"         或者换个端口: python tools\\start.py --desktop --port 8766")


# ====================================================================== 6
def check_backend_boot() -> None:
    section("6. 后端能否真正起来 (进程内起 TestClient 打 /api/health)")
    try:
        os.environ.setdefault("M3_API_KEY", "")
        from fastapi.testclient import TestClient
        from cycling_coach.api.main import app
    except Exception as e:
        check("后端导入", FAIL, f"{type(e).__name__}: {e}\n         常见原因: 依赖没装全, 跑 tools\\start.bat 自动修")
        return

    # 把应用自己打的 INFO 日志压掉 —— 这份报告是要直接粘给别人的,
    # 几十行"知识库导入完成"会把真正的结论埋掉。
    import logging
    prev = {}
    for name in list(logging.root.manager.loggerDict):
        lg = logging.getLogger(name)
        prev[name] = lg.level
        lg.setLevel(logging.CRITICAL)
    logging.getLogger().setLevel(logging.CRITICAL)
    try:
        with TestClient(app) as c:
            r = c.get("/api/health")
            if r.status_code == 200:
                check("GET /api/health", PASS, f"200 {r.json()}")
            else:
                check("GET /api/health", FAIL, f"{r.status_code} {r.text[:200]}")
    except Exception as e:
        check("后端启动", FAIL, f"{type(e).__name__}: {e}")
    finally:
        logging.getLogger().setLevel(logging.WARNING)
        for name, lv in prev.items():
            if lv is not None:
                logging.getLogger(name).setLevel(lv)


# ====================================================================== 7
def check_logs() -> None:
    section("7. 最近的错误日志")
    found = False
    seen: set[Path] = set()
    # 旧的宽泛匹配会把 "FTS5 索引: 500 行" 这种正常日志也当成错误 ——
    # 噪声一多, 用户就不会当真了。只认真正的错误标记。
    MARKERS = ("traceback", "exception", "critical", "| error", "[error]", "error:", "失败:")
    for lf in (data_dir() / ".logs", ROOT / "workspace" / ".logs"):
        if not lf.exists():
            continue
        for f in sorted(lf.glob("*.log")):
            rp = f.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            bad = [ln for ln in text.splitlines()
                   if any(k in ln.lower() for k in MARKERS)]
            if bad:
                found = True
                _lines.append(f"--- {f.name} 里的错误 (最近 8 条) ---")
                for ln in bad[-8:]:
                    _lines.append(f"    {ln[:160]}")
                _lines.append("")
    if not found:
        check("日志", PASS,
              "最近没有 ERROR/Traceback" if (data_dir() / '.logs').exists() else "还没有日志 (没启动过)")


# ======================================================================
def main() -> int:
    _lines.append("=" * 60)
    _lines.append("Cycling Coach 自检报告")
    _lines.append("=" * 60)
    _lines.append(f"时间   : {datetime.now().isoformat(timespec='seconds')}")
    _lines.append(f"系统   : {platform.system()} {platform.release()} ({platform.machine()})")
    _lines.append(f"项目   : {ROOT}")

    check_python()
    check_frontend()
    check_datadir()
    check_database()
    check_ports()
    check_backend_boot()
    check_logs()

    n_fail = sum(1 for _, s, _ in _results if s == FAIL)
    n_warn = sum(1 for _, s, _ in _results if s == WARN)
    n_pass = sum(1 for _, s, _ in _results if s == PASS)

    _lines.append("")
    _lines.append("=" * 60)
    _lines.append(f"结论: {n_pass} 通过 / {n_warn} 警告 / {n_fail} 失败")

    # 先快照正文, 再决定结尾怎么写 —— 之前在 _lines 上自引用 extend,
    # 结果那个"发给别人的"代码块是空的, 用户拿到手的东西没有诊断价值。
    body = list(_lines)

    if n_fail:
        _lines.append("")
        _lines.append("有失败项 —— 上面标 [FAIL] 的就是问题所在, 按提示修。")
        _lines.append("修不好就把下面整段发出去 (已含全部诊断细节):")
        _lines.append("")
        _lines.append("```")
        _lines.extend(body)
        _lines.append("```")
    else:
        _lines.append("环境检查通过。如果界面还是打不开, 试:")
        _lines.append("  1. 关掉所有 Cycling Coach 窗口, 再双击 tools\\start.bat")
        _lines.append("  2. 还不行 → 双击 tools\\diagnose.bat, 把报告发出去")
    _lines.append("=" * 60)

    emit()

    out = data_dir() / ".logs" / "selfcheck.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(_lines), encoding="utf-8")
    print(f"\n完整报告: {out}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
