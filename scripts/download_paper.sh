#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PAPER_DIR="$ROOT_DIR/data/paper"
ARXIV_ID="2506.23719"

mkdir -p "$PAPER_DIR"

curl -L --fail --output "$PAPER_DIR/$ARXIV_ID.pdf" "https://arxiv.org/pdf/$ARXIV_ID"
curl -L --fail --output "$PAPER_DIR/$ARXIV_ID.html" "https://arxiv.org/html/$ARXIV_ID"

echo "Done. Paper files are in $PAPER_DIR"
