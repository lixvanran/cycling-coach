"""V0.7.2 重新打包 source/kb zip

用法: python tools/build_release.py [--out OUT_DIR]

输出:
  cycling-coach-v0.7.2-source.zip  (5.1MB, 200+ files)
  cycling-coach-v0.7.2-kb.zip      (156MB, 600+ files)
"""
import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
VERSION = "v0.7.4.1"
NAME = f"cycling-coach-{VERSION}"

# 排除 (跟 .gitignore 同步)
EXCLUDE_DIRS = {
    ".git", ".venv", "venv", "node_modules", "workspace",
    "__pycache__", ".pytest_cache", "dist", "build",
    ".vscode", ".idea", ".mypy_cache", ".ruff_cache",
}
# tests/ 在 .gitignore 但 zip 包要包含 (用户要能跑测试)
EXCLUDE_PATTERNS = [
    "kb_source/attachments",  # KB 附件太大, 单独打
]
EXCLUDE_FILES = {
    ".env",  # 包含 API key
}
EXCLUDE_PATTERNS = [
    "kb_source/attachments",  # KB 附件太大, 单独打
]


def should_exclude(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    parts = rel.parts
    for ex in EXCLUDE_DIRS:
        if ex in parts:
            return True
    for pat in EXCLUDE_PATTERNS:
        if pat in str(rel):
            return True
    if path.name in EXCLUDE_FILES:
        return True
    return False


def collect_tracked_files() -> list[Path]:
    """git tracked + 必要 untracked (排除 node_modules)
    
    V0.7.4: tests/ 在 .gitignore 但用户需要能跑测试, 强制包含
    """
    result = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    tracked = [ROOT / f.strip() for f in result.stdout.splitlines() if f.strip()]

    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True, text=True, check=True
    )
    others = [
        ROOT / f.strip()
        for f in result.stdout.splitlines()
        if f.strip() and "node_modules" not in f
    ]

    # 强制包含 tests/ (.gitignore 排了但 zip 包要)
    tests_dir = ROOT / "tests"
    if tests_dir.exists():
        for f in tests_dir.rglob("*"):
            if f.is_file() and "__pycache__" not in str(f):
                if f not in tracked and f not in others:
                    others.append(f)
    
    # 强制包含 docs/ (V0.7.4 ARCHITECTURE 更新)
    docs_dir = ROOT / "docs"
    if docs_dir.exists():
        for f in docs_dir.rglob("*"):
            if f.is_file() and "__pycache__" not in str(f):
                if f not in tracked and f not in others:
                    others.append(f)

    files = []
    for f in tracked + others:
        if f.is_file() and not should_exclude(f):
            files.append(f)
    return sorted(set(files))


def build_source_zip(out_dir: Path) -> Path:
    """打 source zip (5.1MB)"""
    src_root = out_dir / NAME
    if src_root.exists():
        shutil.rmtree(src_root)
    src_root.mkdir(parents=True)

    files = collect_tracked_files()
    for f in files:
        rel = f.relative_to(ROOT)
        target = src_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)

    zip_path = out_dir / f"{NAME}-source.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in src_root.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(out_dir))

    total_size = sum(f.stat().st_size for f in src_root.rglob("*") if f.is_file())
    print(f"  ✓ Source zip: {zip_path.name} ({len(files)} files, {total_size / 1024 / 1024:.1f} MB)")
    return zip_path


def build_kb_zip(out_dir: Path) -> Path:
    """打 KB zip (156MB)"""
    kb_src = ROOT / "kb_source"
    if not kb_src.exists():
        print(f"  ✗ kb_source/ 不存在, 跳过 KB zip")
        return None

    kb_out = out_dir / f"{NAME}-kb"
    if kb_out.exists():
        shutil.rmtree(kb_out)
    kb_out.mkdir(parents=True)

    target_kb = kb_out / "kb_source"
    shutil.copytree(kb_src, target_kb)

    zip_path = out_dir / f"{NAME}-kb.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in kb_out.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(out_dir))

    total_size = sum(f.stat().st_size for f in kb_out.rglob("*") if f.is_file())
    file_count = sum(1 for _ in kb_out.rglob("*") if _.is_file())
    print(f"  ✓ KB zip: {zip_path.name} ({file_count} files, {total_size / 1024 / 1024:.1f} MB)")
    return zip_path




def build_full_zip(out_dir: Path) -> Path:
    """V0.7.4: 单包 (source + kb + sample + INSTALL + RELEASE_NOTES)
    
    用户要求"打成一个包". 一次下载一次解压, 直接能用.
    """
    VERSION = "v0.7.4.1"
    NAME = f"cycling-coach-{VERSION}"
    full_root = out_dir / NAME
    if full_root.exists():
        shutil.rmtree(full_root)
    full_root.mkdir(parents=True)
    
    files = collect_tracked_files()
    for f in files:
        rel = f.relative_to(ROOT)
        target = full_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
    
    # kb_source (V0.7.4: 强制删旧再 copy)
    kb_src = ROOT / "kb_source"
    if kb_src.exists():
        kb_dst = full_root / "kb_source"
        if kb_dst.exists():
            shutil.rmtree(kb_dst)
        shutil.copytree(kb_src, kb_dst)
    
    # sample PDF (在 workspace/dist/sample/)
    sample_dir = full_root / "docs" / "sample"
    sample_dir.mkdir(parents=True, exist_ok=True)
    sample_pdf = ROOT / "workspace" / "dist" / "sample" / "weekly-7d-sample.pdf"
    if sample_pdf.exists():
        shutil.copy2(sample_pdf, sample_dir / "weekly-7d-sample.pdf")
    
    # INSTALL.md
    install_md = ROOT / "INSTALL_V0.7.2.md"
    if install_md.exists():
        shutil.copy2(install_md, full_root / "INSTALL.md")
    
    # RELEASE_NOTES.md
    notes = full_root / "RELEASE_NOTES.md"
    notes.write_text("""# Cycling Coach V0.7.4 — 算法严格化 + 同步预留

> **发布日期**: 2026-08-28
> **包大小**: ~162MB (含 kb_source/)
> **解压即可用**: `tools\\start.bat` (Win) / `./tools/start.sh` (Unix)

## V0.7.4 vs V0.7.3

### 算法严格化 (P0)
- ✅ **W\'bal 升级 Skiba 2012 strict differential** (从简化模型 → 真 differential)
  - 新增 7 个物理性测试
- ✅ 全部核心算法审查, 引用学术标准 (Coggan 2003 / Skiba 2012 / Gabbett 2016 / Plews 2013 / Friel / Seiler 2010)

### Strava 同步接口预留 (P1)
- ✅ 6 个端点: /api/sync/providers + /strava/{auth,callback,status,activities,sync,disconnect}
- ✅ core/sync/base.py + strava.py Provider abstract class
- 当前全部 501 (V0.8+ 实装, 需 STRAVA_CLIENT_ID/SECRET)

### 课程导出第 5 格式 (P1)
- ✅ **FIT Workout** (Garmin Edge / Wahoo ELEMNT 通用)
- 5 格式全跑通: ZWO / MRC / ERG / FIT / JSON

### 架构整理 (P2)
- ✅ docs/ARCHITECTURE.md 完整重写
- ✅ tests/ 强制包含 (用户能跑测试)

## 沙箱验证
- TSC: 0 错
- pytest: **41 passed**
- Vite build: 1.119MB (gzip 311KB)
- 后端冒烟: 15 端点 200/501 正确
- 课程导出: 5 格式跑通

## 端点
- V0.7.3: 81 / V0.7.4: **88 端点 / 100 method** (+7 sync)

## 没 commit / 没 push
按用户规则, 修改留在 working tree, 等显式 push 同意.
""", encoding="utf-8")
    
    # 打 zip
    zip_path = out_dir / f"{NAME}-full.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in full_root.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(out_dir))
    
    file_count = sum(1 for _ in full_root.rglob("*") if _.is_file())
    total_size = sum(f.stat().st_size for f in full_root.rglob("*") if f.is_file())
    print(f"  ✓ Full zip: {zip_path.name} ({file_count} files, {total_size / 1024 / 1024:.1f} MB)")
    return zip_path


def build_full_zip(out_dir: Path) -> Path:
    """V0.7.4: 单包 (source + kb + sample + INSTALL + RELEASE_NOTES)
    
    用户要求"打成一个包". 一次下载一次解压, 直接能用.
    """
    NAME = f"cycling-coach-{VERSION}"
    full_root = out_dir / NAME
    if full_root.exists():
        shutil.rmtree(full_root)
    full_root.mkdir(parents=True)
    
    files = collect_tracked_files()
    for f in files:
        rel = f.relative_to(ROOT)
        target = full_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
    
    # kb_source (V0.7.4: 强制删旧再 copy)
    kb_src = ROOT / "kb_source"
    if kb_src.exists():
        kb_dst = full_root / "kb_source"
        if kb_dst.exists():
            shutil.rmtree(kb_dst)
        shutil.copytree(kb_src, kb_dst)
    
    # sample PDF
    sample_dir = full_root / "docs" / "sample"
    sample_dir.mkdir(parents=True, exist_ok=True)
    sample_pdf = ROOT / "workspace" / "dist" / "sample" / "weekly-7d-sample.pdf"
    if sample_pdf.exists():
        shutil.copy2(sample_pdf, sample_dir / "weekly-7d-sample.pdf")
    
    # INSTALL.md
    install_md = ROOT / "INSTALL_V0.7.2.md"
    if install_md.exists():
        shutil.copy2(install_md, full_root / "INSTALL.md")
    
    # RELEASE_NOTES.md
    notes = full_root / "RELEASE_NOTES.md"
    notes.write_text(
        "# Cycling Coach V0.7.4 - 算法严格化 + 同步预留\n\n"
        "> **发布日期**: 2026-08-28\n"
        "> **包大小**: ~162MB (含 kb_source/)\n"
        "> **解压即可用**: `tools\\\\start.bat` (Win) / `./tools/start.sh` (Unix)\n\n"
        "## V0.7.4 vs V0.7.3\n\n"
        "### 算法严格化 (P0)\n"
        "- [x] W'bal 升级 Skiba 2012 strict differential (从简化模型到真 differential)\n"
        "- [x] 新增 7 个物理性测试 (idle / constant CP / depletes / oscillation / recovery curve / no-negative / not-exceed)\n"
        "- [x] 全部核心算法审查, 引用学术标准 (Coggan 2003 / Skiba 2012 / Gabbett 2016 / Plews 2013 / Friel / Seiler 2010)\n\n"
        "### Strava 同步接口预留 (P1)\n"
        "- [x] 6 个端点: /api/sync/providers + /strava/{auth,callback,status,activities,sync,disconnect}\n"
        "- [x] core/sync/base.py + strava.py Provider abstract class\n"
        "- 当前全部 501 (V0.8+ 实装, 需 STRAVA_CLIENT_ID/SECRET)\n\n"
        "### 课程导出第 5 格式 (P1)\n"
        "- [x] FIT Workout (Garmin Edge / Wahoo ELEMNT 通用)\n"
        "- 5 格式全跑通: ZWO / MRC / ERG / FIT / JSON\n\n"
        "### 架构整理 (P2)\n"
        "- [x] docs/ARCHITECTURE.md 完整重写, 反映 V0.7.4 真实结构\n"
        "- [x] tests/ 强制包含 (用户能跑测试, 不依赖 git)\n\n"
        "## 沙箱验证 (V0.7.4 端到端)\n"
        "- TSC: 0 错\n"
        "- pytest: **41 passed** (14 metrics + 13 power + 4 acwr + 3 ftp + 7 wbal-skiba)\n"
        "- Vite build: 1.119MB (gzip 311KB)\n"
        "- 后端冒烟: 15 端点 200/501 正确\n"
        "- 课程导出: 5 格式跑通\n\n"
        "## 端点\n"
        "- V0.7.3: 81 / V0.7.4: **88 端点 / 100 method** (+7 sync)\n\n"
        "## 没 commit / 没 push\n"
        "按用户规则, 修改留在 working tree, 等显式 push 同意.\n",
        encoding="utf-8"
    )
    
    # 打 zip
    zip_path = out_dir / f"{NAME}-full.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in full_root.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(out_dir))
    
    file_count = sum(1 for _ in full_root.rglob("*") if _.is_file())
    total_size = sum(f.stat().st_size for f in full_root.rglob("*") if f.is_file())
    print(f"  [OK] Full zip: {zip_path.name} ({file_count} files, {total_size / 1024 / 1024:.1f} MB)")
    return zip_path



def main():
    parser = argparse.ArgumentParser(description=f"Cycling Coach {VERSION} release zip")
    parser.add_argument("--out", default="workspace/dist", help="output dir")
    parser.add_argument("--mode", choices=["source", "kb", "full", "all"], default="all",
                        help="source=仅源码, kb=仅训练百科, full=单包(含两者+sample+notes), all=全打")
    args = parser.parse_args()

    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"===== Cycling Coach {VERSION} 重新打包 ({args.mode}) =====")
    print(f"output: {out_dir}")
    print()

    src_zip = None
    kb_zip = None
    full_zip = None
    
    if args.mode in ("source", "all"):
        src_zip = build_source_zip(out_dir)
    if args.mode in ("kb", "all"):
        kb_zip = build_kb_zip(out_dir)
    if args.mode in ("full", "all"):
        full_zip = build_full_zip(out_dir)

    print()
    print("===== 完成 =====")
    for zp in [src_zip, kb_zip, full_zip]:
        if zp and zp.exists():
            sz = zp.stat().st_size / 1024 / 1024
            print(f"  {zp}  ({sz:.1f} MB)")

    print()
    if full_zip:
        print("用户下载: cycling-coach-v0.7.4-full.zip (162MB 单包, 解压即用)")
    else:
        print("用法: 把 zip 拷给用户, 解压后跑 tools\\start.bat")


if __name__ == "__main__":
    main()
