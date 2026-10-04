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
VERSION = "v0.9.0"
NAME = f"cycling-coach-{VERSION}"

# 排除 (跟 .gitignore 同步)
EXCLUDE_DIRS = {
    ".git", ".venv", "venv", "node_modules", "workspace",
    "__pycache__", ".pytest_cache", "dist", "build",
    ".vscode", ".idea", ".mypy_cache", ".ruff_cache",
    "cycling-coach-v0.7.4.1-backup",  # V0.7.5.1 排除历史备份
    "cycling-coach-v0.7.4.1",  # V0.7.4.2 排除历史 zip 目录
    "cycling-coach-v0.9.0",  # 排除当前 zip 输出目录
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

    # 强制包含前端 build 产物 cycling_coach/static/  —— 这一条是 P0, 不是可选优化。
    #
    # .gitignore 里有 `cycling_coach/static/`, 所以 `git ls-files` 拿到 0 个文件,
    # `git ls-files --others --exclude-standard` 也因为尊重 .gitignore 拿不到。
    # 而 start.bat 默认 --desktop, 桌面模式硬依赖这个目录 (start.py 的
    # find_frontend_dist() 只认它和 apps/web/dist)。
    #
    # 后果: 官方 source zip 里没有 static -> Windows 用户双击 start.bat ->
    # "桌面模式需要前端 build 产物, 但没找到" -> 唯一解法是让他装 Node + pnpm,
    # 而 start.bat 的文件头恰恰承诺普通 Windows 用户不需要装 Node。
    # 这条路径在开发机上永远看不见, 因为本地有 build 产物。
    static_dir = ROOT / "cycling_coach" / "static"
    if static_dir.exists() and (static_dir / "index.html").exists():
        for f in static_dir.rglob("*"):
            if f.is_file() and "__pycache__" not in str(f):
                if f not in tracked and f not in others:
                    others.append(f)
    else:
        # 不能安静地打一个必然打不开的包 —— 直接让发布流程失败。
        raise SystemExit(
            "[build_release] 前端 build 产物缺失, 拒绝打包。\n"
            "  原因: 不带 cycling_coach/static/ 的包, Windows 用户双击 start.bat 会直接失败。\n"
            # V0.9.0: 原来这里写的是 `npx vite build` —— 而那恰恰是**跳过类型检查**的
            # 命令。verifier 指出: 这一轮的核心成果就是"把 tsc && vite build 修通",
            # 但没有任何自动环节会跑它, 安全网装在了没插电的插座上。
            # 这里只给"会跑 tsc"的那条命令。
            "  先跑: cd apps/web && pnpm build   (= tsc && vite build, 含类型检查)\n"
            "  (或: python tools/start.py --desktop --install, 会自动 build)"
        )

    # V0.9.0: 新鲜度断言 —— 防止把过期的 static/ 打进包。
    # 这个缺口很隐蔽: 改了前端源码忘了重新 build, 包里带的是上一版产物,
    # 而且**所有检查都会通过**(包是完整的, 静态资源都在, 页面也能打开),
    # 只是内容是旧的。以前只有一个"存不存在"的检查, 查不出"是不是新的"。
    if static_dir.exists():
        _src = ROOT / "apps" / "web" / "src"
        _newest_src = max((f.stat().st_mtime for f in _src.rglob("*") if f.is_file()), default=0)
        _newest_out = max((f.stat().st_mtime for f in static_dir.rglob("*") if f.is_file()), default=0)
        if _newest_src > _newest_out + 1:
            raise SystemExit(
                "[build_release] static/ 比 src/ 旧, 拒绝打包。\n"
                "  改了前端但没重新 build —— 打进去的会是上一版界面, 而所有检查都会通过。\n"
                "  先跑: cd apps/web && pnpm build"
            )

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
    import zipfile
    VERSION = "v0.9.0"
    NAME = f"cycling-coach-{VERSION}"
    zip_path = out_dir / f"{NAME}-full.zip"
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
    
    # kb_source (强制删旧再 copy)
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
    install_md = ROOT / "INSTALL_V0.9.0.md"
    if install_md.exists():
        shutil.copy2(install_md, full_root / "INSTALL.md")
    
    # RELEASE_NOTES.md (V0.7.4.2: 从根目录 / 拷贝)
    notes = full_root / "RELEASE_NOTES.md"
    release_notes_src = ROOT / "RELEASE_NOTES.md"
    if release_notes_src.exists():
        shutil.copy2(release_notes_src, notes)
    else:
        # 兜底: 找 cycling-coach-v{VERSION}/RELEASE_NOTES.md
        for p in ROOT.glob(f"cycling-coach-{VERSION}/RELEASE_NOTES.md"):
            shutil.copy2(p, notes)
            break
    
    # 打 zip
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
