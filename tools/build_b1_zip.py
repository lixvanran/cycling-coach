"""V0.8.3 B1 zip — 集成验证后打 zip 给用户预览

按 V0.8.2 build_release.py 同样规则:
- 排除 .venv .ruff_cache __pycache__ node_modules workspace/ .env _review/kb_full/ .git/*
- 包含 cycling_coach/static/ (新 build)
- 包含 .github/

用法: python tools/build_b1_zip.py [--out OUT_DIR]
默认输出到 /workspace/cycling-coach-v0.8.3-b1-YYYYMMDD.zip
"""
import argparse
import os
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
DATE = datetime.now().strftime("%Y%m%d")
VERSION = "v0.8.3-b1"
NAME = f"cycling-coach-{VERSION}-{DATE}"

# 跟 .gitignore 同步 (V0.8.2 同款)
EXCLUDE_DIRS = {
    ".git", ".venv", "venv", "node_modules", "workspace",
    "__pycache__", ".pytest_cache", ".ruff_cache",
    ".vscode", ".idea", ".mypy_cache",
}
# 注: 不排 cycling_coach/static/ — B1 要求包含新 build
EXCLUDE_PATTERNS = [
    "kb_source/attachments",  # KB 附件太大
    "_review/kb_full",        # 跟 V0.8.2 同款
    "workspace/",             # 运行时 SQLite
]
EXCLUDE_FILES = {
    ".env", ".env.local",
}


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


def collect_files() -> list[Path]:
    """git tracked + 必要 untracked (强制包含 tests/, docs/, _review/, cycling_coach/static/)"""
    files: list[Path] = []

    # git config -c core.quotePath= 关掉路径 quote (否则 zh-CN 路径会被引号包住, Path 解析失败)
    git_env = {"GIT_CONFIG_GLOBAL": "/dev/null"}
    git_common = ["git", "-c", "core.quotePath="]

    # 1) git tracked files
    result = subprocess.run(
        git_common + ["ls-files"], cwd=ROOT, capture_output=True, text=True, check=True, env={**os.environ, **git_env}
    )
    tracked = [ROOT / f.strip() for f in result.stdout.splitlines() if f.strip()]

    # 2) git untracked but not ignored
    result = subprocess.run(
        git_common + ["ls-files", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True, text=True, check=True, env={**os.environ, **git_env}
    )
    others = [
        ROOT / f.strip()
        for f in result.stdout.splitlines()
        if f.strip() and "node_modules" not in f
    ]

    # 3) 强制包含: tests/ (即使 .gitignore 排了)
    tests_dir = ROOT / "tests"
    if tests_dir.exists():
        for f in tests_dir.rglob("*"):
            if f.is_file() and "__pycache__" not in str(f):
                if f not in tracked and f not in others:
                    others.append(f)

    # 4) 强制包含: docs/ (ARCHITECTURE)
    docs_dir = ROOT / "docs"
    if docs_dir.exists():
        for f in docs_dir.rglob("*"):
            if f.is_file() and "__pycache__" not in str(f):
                if f not in tracked and f not in others:
                    others.append(f)

    # 5) 强制包含: _review/ (V0.8.3 plan, B1 deliverable)
    review_dir = ROOT / "_review"
    if review_dir.exists():
        for f in review_dir.rglob("*"):
            if f.is_file() and "_review/kb_full" not in str(f):
                if f not in tracked and f not in others:
                    others.append(f)

    # 6) 强制包含: cycling_coach/static/ (.gitignore 排了但 B1 要求带新 build)
    static_dir = ROOT / "cycling_coach" / "static"
    if static_dir.exists():
        for f in static_dir.rglob("*"):
            if f.is_file():
                if f not in tracked and f not in others:
                    others.append(f)

    files = []
    for f in tracked + others:
        if f.is_file() and not should_exclude(f):
            files.append(f)
    return sorted(set(files))


def build_zip(out_dir: Path) -> Path:
    """打 zip, 顶层目录名 cycling-coach-{VERSION}-{DATE}/"""
    src_root = out_dir / NAME
    if src_root.exists():
        shutil.rmtree(src_root)
    src_root.mkdir(parents=True)

    files = collect_files()
    for f in files:
        rel = f.relative_to(ROOT)
        target = src_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)

    zip_path = out_dir / f"{NAME}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in src_root.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(out_dir))

    file_count = sum(1 for _ in src_root.rglob("*") if _.is_file())
    total_size = sum(f.stat().st_size for f in src_root.rglob("*") if f.is_file())
    print(f"  [OK] {zip_path.name}")
    print(f"       {file_count} files, {total_size / 1024 / 1024:.1f} MB raw")
    print(f"       zip size: {zip_path.stat().st_size / 1024 / 1024:.1f} MB")
    return zip_path


def main():
    parser = argparse.ArgumentParser(description=f"Cycling Coach {VERSION} zip")
    parser.add_argument("--out", default="/workspace",
                        help="output dir (default /workspace)")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"===== Cycling Coach {VERSION} zip =====")
    print(f"output: {out_dir}")
    print()

    zip_path = build_zip(out_dir)

    print()
    print(f"用户预览: {zip_path}")
    print(f"         (不 commit / 不 push, 按用户硬规则)")


if __name__ == "__main__":
    main()