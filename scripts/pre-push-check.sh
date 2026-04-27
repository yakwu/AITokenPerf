#!/bin/bash
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "$ROOT_DIR"

if [[ "${SKIP_PRE_PUSH_CHECKS:-}" == "1" ]]; then
  echo "⏭️  Pre-push checks skipped by SKIP_PRE_PUSH_CHECKS=1"
  exit 0
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$BRANCH" != "dev" && "$BRANCH" != "main" ]]; then
  echo "⏭️  Pre-push checks skipped on branch $BRANCH"
  exit 0
fi

if [[ "${RUN_FULL_E2E:-}" == "1" ]]; then
  echo "🎭 RUN_FULL_E2E=1, running full E2E suite..."
  exec bash scripts/e2e-run.sh "$@"
fi

UPSTREAM=""
if UPSTREAM="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null)"; then
  BASE="$(git merge-base HEAD "$UPSTREAM")"
  CHANGED_FILES="$(git diff --name-only "$BASE"...HEAD)"
else
  CHANGED_FILES="$(git diff --name-only HEAD~1...HEAD 2>/dev/null || true)"
fi

if [[ -z "$CHANGED_FILES" ]]; then
  echo "✅ No pushed file changes detected"
  exit 0
fi

echo "🔍 Pre-push: running fast checks for pushed changes"

DOCS_ONLY=1
while IFS= read -r file; do
  [[ -z "$file" ]] && continue
  case "$file" in
    *.md|docs/*|.gitignore)
      ;;
    *)
      DOCS_ONLY=0
      ;;
  esac
done <<< "$CHANGED_FILES"

if [[ "$DOCS_ONLY" == "1" ]]; then
  echo "✅ Docs/config-only push; skipping test suites"
  exit 0
fi

BACKEND_CHANGED=0
FRONTEND_CHANGED=0
E2E_CHANGED=0

while IFS= read -r file; do
  [[ -z "$file" ]] && continue
  case "$file" in
    app/*.py|tests/*.py|scripts/*.py)
      BACKEND_CHANGED=1
      ;;
    frontend/*|frontend/**/*|package.json|bun.lock|frontend/package.json|frontend/bun.lock)
      FRONTEND_CHANGED=1
      ;;
    e2e/*|e2e/**/*|playwright.config.js|scripts/e2e-run.sh)
      E2E_CHANGED=1
      ;;
  esac
done <<< "$CHANGED_FILES"

if [[ "$BACKEND_CHANGED" == "1" ]]; then
  if [[ -x "venv/bin/python" ]]; then
    PYTHON_BIN="venv/bin/python"
  elif [[ -x ".venv/bin/python" ]]; then
    PYTHON_BIN=".venv/bin/python"
  else
    PYTHON_BIN="python"
  fi

  echo "🐍 Backend changed: compiling Python files"
  "$PYTHON_BIN" -m py_compile app/*.py

  CHANGED_TESTS=()
  while IFS= read -r line; do
    [[ -n "$line" ]] && CHANGED_TESTS+=("$line")
  done < <(printf "%s\n" "$CHANGED_FILES" | grep -E '^tests/.*\.py$' || true)
  if [[ "${#CHANGED_TESTS[@]}" -gt 0 ]]; then
    echo "🧪 Running changed pytest files"
    "$PYTHON_BIN" -m pytest -q "${CHANGED_TESTS[@]}"
  fi
fi

if [[ "$FRONTEND_CHANGED" == "1" ]]; then
  echo "🧪 Frontend changed: running vitest"
  (cd frontend && ./node_modules/.bin/vitest run)

  echo "🏗️  Frontend changed: running build"
  (cd frontend && bun run build)
fi

if [[ "$E2E_CHANGED" == "1" ]]; then
  echo "🎭 E2E files changed: running full E2E suite"
  exec bash scripts/e2e-run.sh "$@"
fi

echo "✅ Fast pre-push checks passed"
