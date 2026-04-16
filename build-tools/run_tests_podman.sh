#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# run_tests_podman.sh — Podman-based parallel test runner
#
# Builds a test image, then spins up parallel containers for:
#   1. Core unit tests
#   2. Frontend tests — test_frontend.py
#   3. Frontend tests — test_profile_integration.py + test_workflow_integration.py
#
# Results are collected as JUnit XML in test-results/.
#
# Usage:
#   bash build-tools/run_tests_podman.sh
#   bash build-tools/run_tests_podman.sh --no-build   # skip image rebuild
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

IMAGE="spotyvibe-test:latest"
RESULTS_DIR="$PROJECT_ROOT/test-results"
mkdir -p "$RESULTS_DIR"

# ── Build image (unless --no-build) ──────────────────────────
if [[ "${1:-}" != "--no-build" ]]; then
  echo "═══ Building test image ═══"
  podman build -f Dockerfile.test -t "$IMAGE" .
fi

# ── Helper: run a container and extract results ──────────────
run_suite() {
  local NAME="$1"
  shift
  echo "═══ Starting: $NAME ═══"
  podman run --rm --name "sv-test-$NAME" \
    -v "$RESULTS_DIR:/app/test-results:z" \
    "$IMAGE" "$@" &
}

# ── Launch 3 containers in parallel ──────────────────────────
run_suite core \
  core/tests/ -v --tb=short --junitxml=/app/test-results/core.xml

run_suite frontend-main \
  frontend/tests/test_frontend.py -v --tb=short -n auto \
  --junitxml=/app/test-results/frontend-main.xml

run_suite frontend-integration \
  frontend/tests/test_profile_integration.py \
  frontend/tests/test_workflow_integration.py \
  -v --tb=short -n auto \
  --junitxml=/app/test-results/frontend-integration.xml 2>/dev/null || true

# ── Wait for all ─────────────────────────────────────────────
CORE_EXIT=0
FRONTEND_MAIN_EXIT=0
FRONTEND_INT_EXIT=0

wait %1 || CORE_EXIT=$?
wait %2 || FRONTEND_MAIN_EXIT=$?
wait %3 || FRONTEND_INT_EXIT=$?

# ── Summary ──────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════"
echo "  Podman Test Summary"
echo "═══════════════════════════════════"
for pair in "Core:$CORE_EXIT" "Frontend-main:$FRONTEND_MAIN_EXIT" "Frontend-integration:$FRONTEND_INT_EXIT"; do
  NAME="${pair%%:*}"
  CODE="${pair##*:}"
  if [[ "$CODE" -eq 0 ]]; then
    echo "  ✅ $NAME  PASSED"
  else
    echo "  ❌ $NAME  FAILED (exit $CODE)"
  fi
done
echo "═══════════════════════════════════"
echo "  XML results in test-results/"
echo "═══════════════════════════════════"

exit $((CORE_EXIT + FRONTEND_MAIN_EXIT + FRONTEND_INT_EXIT))

