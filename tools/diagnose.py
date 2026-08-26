#!/usr/bin/env python3
"""生成诊断报告(diagnose.txt)

Windows 关键修复:node/pnpm/npm 在 Win 上是 .cmd shim,
subprocess.run([name, ...]) 找不到时抛 WinError 2。
用 shutil.which 找 .cmd/.exe 真实路径,跟 start.py 一样。
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
WORKSPACE_DIR = ROOT / "workspace"
LOG_FILE = WORKSPACE_DIR / ".logs" / "sidecar.log"
OUT_FILE = ROOT / "diagnose.txt"


def _resolve_cmd(name: str) -> str | None:
    """在 Windows 上找 .cmd shim 真实路径,Linux/macOS 直接 which"""
    # 1. 直接 which
    p = shutil.which(name)
    if p:
        return p
    # 2. Windows 上找 .cmd / .exe / .bat
    if sys.platform == "win32":
        for ext in (".cmd", ".exe", ".bat", ".ps1"):
            p2 = shutil.which(name + ext)
            if p2:
                return p2
    return None


def _run_safe(cmd_args: list[str]) -> str:
    """跑子命令,Windows .cmd 用 cmd /c 包装,失败返回错误信息"""
    try:
        if sys.platform == "win32":
            cmd_str = subprocess.list2cmdline(cmd_args)
            r = subprocess.run(
                ["cmd", "/c", cmd_str],
                capture_output=True, text=True, timeout=10,
            )
        else:
            r = subprocess.run(cmd_args, capture_output=True, text=True, timeout=10)
        out = (r.stdout or r.stderr or "").strip()
        return out or "(无输出)"
    except FileNotFoundError as e:
        return f"(未安装: {e})"
    except subprocess.TimeoutExpired:
        return "(超时)"
    except Exception as e:
        return f"(错误: {e})"


def main() -> int:
    lines: list[str] = []
    lines.append("===== Cycling Coach 诊断报告 =====\n")
    lines.append(f"时间: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"系统: {platform.system()} {platform.release()}")
    lines.append(f"Python: {sys.version}")
    lines.append("")

    lines.append("===== 环境 =====")
    for name in ["node", "npm", "pnpm"]:
        path = _resolve_cmd(name)
        if not path:
            lines.append(f"{name}: (未安装)")
            continue
        ver = _run_safe([name, "--version"])
        lines.append(f"{name}: {ver}  ({path})")
    lines.append("")

    lines.append("===== 目录检查 =====")
    for d in [".venv", "cycling_coach", "apps/web", "workspace",
              "node_modules", "apps/web/node_modules",
              ".npmrc", "pnpm-workspace.yaml"]:
        p = ROOT / d
        if d.endswith((".yaml", ".npmrc")):
            lines.append(f"{d}: {'OK' if p.is_file() else 'MISSING'}")
        else:
            lines.append(f"{d}: {'OK' if p.exists() else 'MISSING'}")
    lines.append("")

    lines.append("===== 关键 binary 检查 =====")
    esbuild_in_workspace = ROOT / "node_modules" / ".pnpm"
    if esbuild_in_workspace.exists():
        esbuild_pkgs = [d.name for d in esbuild_in_workspace.iterdir()
                        if d.name.startswith("esbuild@")]
        lines.append(f"workspace .pnpm esbuild 包: {esbuild_pkgs or '无'}")
    else:
        lines.append("workspace .pnpm 目录: 不存在")
    vite_bin = ROOT / "apps" / "web" / "node_modules" / ".bin" / (
        "vite.cmd" if platform.system() == "Windows" else "vite"
    )
    lines.append(f"vite binary (apps/web): {'OK' if vite_bin.exists() else 'MISSING'}")
    esbuild_apps = ROOT / "apps" / "web" / "node_modules" / ".bin" / (
        "esbuild.cmd" if platform.system() == "Windows" else "esbuild"
    )
    lines.append(f"esbuild binary (apps/web/.bin): {'OK' if esbuild_apps.exists() else 'MISSING (pnpm workspace 模式正常)'}")
    lines.append("")

    lines.append("===== 端口检查 =====")
    for port in [8765, 1420]:
        try:
            if platform.system() == "Windows":
                out = subprocess.run(
                    ["netstat", "-ano"], capture_output=True, text=True, timeout=10,
                ).stdout
            else:
                out = subprocess.run(
                    ["lsof", "-i", f":{port}"], capture_output=True, text=True, timeout=10,
                ).stdout
            if str(port) in out:
                lines.append(f"端口 {port}: 已被占用")
            else:
                lines.append(f"端口 {port}: 空闲")
        except FileNotFoundError:
            lines.append(f"端口 {port}: (netstat/lsof 不可用)")
        except Exception as e:
            lines.append(f"端口 {port}: (检查失败: {e})")
    lines.append("")

    lines.append("===== 后端日志(最近 50 行) =====")
    if LOG_FILE.exists():
        try:
            text = LOG_FILE.read_text(encoding="utf-8", errors="ignore")
            tail = "\n".join(text.splitlines()[-50:])
            lines.append(tail)
        except Exception as e:
            lines.append(f"读取失败: {e}")
    else:
        lines.append("(无日志,后端可能未启动)")

    OUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"诊断报告已写入: {OUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
