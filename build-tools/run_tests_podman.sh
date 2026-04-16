#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# run_tests_podman.sh — Podman-based parallel test runner
#
# Builds a test image, then spins up parallel containers for:
#   1. Core unit tests
#   2. Frontend — page load, navigation, modals
#   3. Frontend — profile, generation, edge cases
#   4. Frontend — onboarding + integration tests
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

# ── Launch 5 containers in parallel ──────────────────────────
run_suite core \
  core/tests/ -v --tb=short --junitxml=/app/test-results/core.xml

run_suite frontend-ui \
  frontend/tests/test_page_load.py \
  frontend/tests/test_navigation.py \
  frontend/tests/test_modals.py \
  -v --tb=short \
  --junitxml=/app/test-results/frontend-ui.xml

run_suite frontend-features \
  frontend/tests/test_profile.py \
  frontend/tests/test_generation.py \
  frontend/tests/test_edge_cases.py \
  -v --tb=short \
  --junitxml=/app/test-results/frontend-features.xml

run_suite frontend-onboarding \
  frontend/tests/test_onboarding.py \
  frontend/tests/test_profile_integration.py \
  -v --tb=short \
  --junitxml=/app/test-results/frontend-onboarding.xml

run_suite frontend-wf \
  frontend/tests/test_wf_onboarding.py \
  frontend/tests/test_wf_generate_create.py \
  frontend/tests/test_wf_generate_append.py \
  frontend/tests/test_wf_generate_override.py \
  frontend/tests/test_wf_analysis.py \
  frontend/tests/test_wf_quickstart_openai.py \
  frontend/tests/test_wf_quickstart_spotify.py \
  -v --tb=short \
  --junitxml=/app/test-results/frontend-wf.xml

# ── Wait for all ─────────────────────────────────────────────
EXIT_CORE=0
EXIT_UI=0
EXIT_FEAT=0
EXIT_OB=0
EXIT_WF=0

wait %1 || EXIT_CORE=$?
wait %2 || EXIT_UI=$?
wait %3 || EXIT_FEAT=$?
wait %4 || EXIT_OB=$?
wait %5 || EXIT_WF=$?

# ── Summary ──────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════"
echo "  Podman Test Summary"
echo "═══════════════════════════════════"
for pair in "Core:$EXIT_CORE" "Frontend-UI:$EXIT_UI" "Frontend-Features:$EXIT_FEAT" "Frontend-Onboarding:$EXIT_OB" "Workflow:$EXIT_WF"; do
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

exit $((EXIT_CORE + EXIT_UI + EXIT_FEAT + EXIT_OB + EXIT_WF))
