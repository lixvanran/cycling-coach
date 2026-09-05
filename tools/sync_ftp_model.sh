#!/bin/bash
# sync_ftp_model.sh — 从 lixvanran/ftp-predictor 拉最新 .joblib
# Usage: ./tools/sync_ftp_model.sh [version]
#  默认: 拉最新 release
#  指定: ./tools/sync_ftp_model.sh v1.0.0
#
# 兼容 private 仓库: GitHub release 拿不到时, 自动 fallback 到本地源
#   - 环境变量 FTP_PREDICTOR_SRC: 本地源路径 (默认 /workspace/ftp-predictor)
#
# 输出目录:
#   workspace/models/ftp_predictor/<version>/
#     ├── best_model.joblib
#     ├── conformal_models.joblib
#     └── metadata.json

set -e
VERSION="${1:-latest}"
REPO="lixvanran/ftp-predictor"
TARGET_DIR="workspace/models/ftp_predictor"
LOCAL_SRC="${FTP_PREDICTOR_SRC:-/workspace/ftp-predictor}"

echo "=== 同步 ftp-predictor 模型 ==="
echo "  Repo: $REPO"
echo "  Version: $VERSION"
echo "  Target: $TARGET_DIR"
echo "  Local fallback: $LOCAL_SRC"

# 1) 查 release URL (private repo 不会成功, 当 tag 取不到时 fallback)
REMOTE_OK=0
if [ "$VERSION" = "latest" ]; then
    echo "查最新 release..."
    TAG_JSON=$(curl -s "https://api.github.com/repos/$REPO/releases/latest" || echo "")
    VERSION=$(echo "$TAG_JSON" | python -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('tag_name', 'v1.0.0'))" 2>/dev/null || echo "v1.0.0")
    if [ -z "$VERSION" ]; then
        VERSION="v1.0.0"
    fi
    echo "  解析: $VERSION"
    if echo "$TAG_JSON" | grep -q "tag_name"; then
        REMOTE_OK=1
    fi
fi

# 2) 拉 .joblib
DEST="$TARGET_DIR/$VERSION"
mkdir -p "$DEST"
BASE_URL="https://github.com/$REPO/releases/download/$VERSION"

for f in best_model.joblib conformal_models.joblib; do
    if [ -f "$DEST/$f" ]; then
        echo "  跳过 (已存在): $DEST/$f"
        continue
    fi

    DOWNLOADED=0
    if [ "$REMOTE_OK" = "1" ]; then
        echo "下载 $f (GitHub release)..."
        if curl -sLf -o "$DEST/$f" "$BASE_URL/$f"; then
            DOWNLOADED=1
        fi
    fi

    if [ "$DOWNLOADED" = "0" ]; then
        # Fallback 1: raw.githubusercontent.com main 分支
        echo "下载 $f (raw.githubusercontent main)..."
        if curl -sLf -o "$DEST/$f" "https://raw.githubusercontent.com/$REPO/main/artifacts/models/$f" 2>/dev/null; then
            DOWNLOADED=1
        fi
    fi

    if [ "$DOWNLOADED" = "0" ]; then
        # Fallback 2: 本地源 (开发场景, ftp-predictor 仓库在 /workspace)
        LOCAL_FILE="$LOCAL_SRC/artifacts/models/$f"
        if [ -f "$LOCAL_FILE" ]; then
            echo "  本地源: $LOCAL_FILE"
            cp "$LOCAL_FILE" "$DEST/$f"
            DOWNLOADED=1
        else
            echo "  ERROR: 本地源也不存在 ($LOCAL_FILE)" >&2
            exit 1
        fi
    fi

    if [ "$DOWNLOADED" = "1" ] && [ -f "$DEST/$f" ]; then
        echo "  OK: $(du -h "$DEST/$f" | awk '{print $1}')"
    fi
done

# 3) 生成 metadata.json
if [ -f "$DEST/best_model.joblib" ]; then
    echo "生成 metadata..."
    python -c "
import joblib, json, datetime
d = joblib.load('$DEST/best_model.joblib')
meta = {
    'version': '$VERSION',
    'synced_at': datetime.datetime.now().isoformat(),
    'model_name': d.get('model_name', 'unknown'),
    'feature_cols': d.get('feature_cols', []),
    'target_col': d.get('target_col', 'ftp'),
    'cv_mae_mean': float(d.get('cv_mae_mean', 0)),
    'cv_r2_mean': float(d.get('cv_r2_mean', 0)),
    'n_features': len(d.get('feature_cols', [])),
}
with open('$DEST/metadata.json', 'w', encoding='utf-8') as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)
print('  metadata: ' + '$DEST/metadata.json')
print('  features: ' + str(len(meta['feature_cols'])))
print('  cv_mae: ' + str(round(meta['cv_mae_mean'], 2)) + 'W')
"
fi

echo "=== 完成 ==="
ls -la "$DEST"
