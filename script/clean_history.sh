#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ "${1:-}" != "--skip-build" ]]; then
  echo "[1/3] Build frontend (web_ui/dist)..."
  (cd web_ui && npm run build)
else
  echo "[1/3] Skip frontend build (--skip-build)"
fi

echo "[2/3] Sync static with latest dist (delete stale files)..."
rsync -a --delete web_ui/dist/ static/

echo "[3/3] Remove Python cache files..."
find . -type f -name '*.pyc' -delete
find . -type d -name '__pycache__' -empty -delete

echo "Done. Historical generated files are cleaned."
