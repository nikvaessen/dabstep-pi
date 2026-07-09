#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_ROOT="$ROOT_DIR/data"
DATA_DIR="$DATA_ROOT/dabstep"
DATASET_URL="https://huggingface.co/datasets/adyen/dabstep"

# Only fetch the benchmark inputs needed to run agents. The Hugging Face repo
# also contains leaderboard submissions and task score artifacts, which are large.
SPARSE_PATHS=(
  /README.md
  /LICENSE
  /data/context/**
  /data/tasks/**
)
LFS_INCLUDE="data/context/**,data/tasks/**"

mkdir -p "$DATA_DIR"

TMP_REPO="$(mktemp -d "$ROOT_DIR/.dabstep-source.XXXXXX")"
cleanup() {
  rm -rf "$TMP_REPO"
}
trap cleanup EXIT

# Clean up layouts created by earlier versions of this script.
rm -rf "$DATA_ROOT/context" "$DATA_ROOT/tasks" "$DATA_ROOT/.source" "$DATA_DIR/.source" "$DATA_DIR/data"
rm -f "$DATA_ROOT/README.md" "$DATA_ROOT/LICENSE"

if [ -d "$DATA_ROOT/.git" ]; then
  echo "Error: $DATA_ROOT is an old dataset git checkout. Remove it and rerun this script." >&2
  exit 1
fi

echo "Downloading DABstep dataset inputs into $DATA_DIR"
GIT_LFS_SKIP_SMUDGE=1 git clone --filter=blob:none --sparse "$DATASET_URL" "$TMP_REPO"
git -C "$TMP_REPO" sparse-checkout set --no-cone "${SPARSE_PATHS[@]}"

if command -v git-lfs >/dev/null 2>&1; then
  git -C "$TMP_REPO" lfs pull --include="$LFS_INCLUDE" --exclude="data/submissions/**,data/task_scores/**"
else
  echo "Warning: git-lfs not found; large dataset files may not have been downloaded." >&2
fi

rm -rf "$DATA_DIR/context" "$DATA_DIR/tasks"
rm -f "$DATA_DIR/README.md" "$DATA_DIR/LICENSE"
cp -a "$TMP_REPO/data/context" "$DATA_DIR/context"
cp -a "$TMP_REPO/data/tasks" "$DATA_DIR/tasks"
cp -a "$TMP_REPO/README.md" "$DATA_DIR/README.md"
cp -a "$TMP_REPO/LICENSE" "$DATA_DIR/LICENSE"

echo "Done. Dataset inputs are in $DATA_DIR/{context,tasks}"
