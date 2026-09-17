#!/usr/bin/env bash
# Mirrors .github/workflows/ci.yml — run this before pushing to catch what
# CI would catch, without waiting on a round trip through GitHub Actions.
# No live LLM calls happen here (see backend/README.md for the manual
# scripted-conversation validation against the real Anthropic API).
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "== backend: pytest =="
(cd "$root/backend" && uv run pytest -q)

echo "== backend: ruff =="
(cd "$root/backend" && uv run ruff check src tests scripts)

echo "== frontend: typecheck =="
(cd "$root/frontend" && npx tsc -b)

echo "== frontend: build =="
(cd "$root/frontend" && npm run build)

echo "== frontend: lint =="
(cd "$root/frontend" && npm run lint)

echo "== all checks passed =="
