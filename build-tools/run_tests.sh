#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# run_tests.sh — Parallel test runner (no containers)
#
# Runs core (unit) and frontend (Playwright) tests in parallel.
# Frontend tests are split into 3 self-contained parallel groups.
# Each group runs sequentially with its own Flask server + browser.
#
# Usage:
#   bash build-tools/run_tests.sh          # run all suites
#   bash build-tools/run_tests.sh core     # core only
#   bash build-tools/run_tests.sh frontend # frontend only
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

SUITE="${1:-all}"
EXIT_CORE=0
EXIT_FE_UI=0
EXIT_FE_FEAT=0
EXIT_FE_WF=0

mkdir -p test-results

run_core() {
  echo "═══ Core tests ═══"
  python -m pytest core/tests/ -v --tb=short --junitxml=test-results/core.xml 2>&1 | tee test-results/core.log
  return "${PIPESTATUS[0]}"
}

run_frontend_ui() {
  echo "═══ Frontend UI tests (page load, navigation, modals) ═══"
  python -m pytest \
    frontend/tests/test_page_load.py \
    frontend/tests/test_navigation.py \
    frontend/tests/test_modals.py \
    -v --tb=short --junitxml=test-results/frontend-ui.xml 2>&1 | tee test-results/frontend-ui.log
  return "${PIPESTATUS[0]}"
}

run_frontend_features() {
  echo "═══ Frontend feature + onboarding tests ═══"
  python -m pytest \
    frontend/tests/test_profile.py \
    frontend/tests/test_generation.py \
    frontend/tests/test_edge_cases.py \
    frontend/tests/test_onboarding.py \
    frontend/tests/test_profile_integration.py \
    -v --tb=short --junitxml=test-results/frontend-features.xml 2>&1 | tee test-results/frontend-features.log
  return "${PIPESTATUS[0]}"
}

run_frontend_wf() {
  echo "═══ Workflow integration tests ═══"
  python -m pytest \
    frontend/tests/test_wf_onboarding.py \
    frontend/tests/test_wf_generate_create.py \
    frontend/tests/test_wf_generate_append.py \
    frontend/tests/test_wf_generate_override.py \
    frontend/tests/test_wf_analysis.py \
    frontend/tests/test_wf_quickstart_openai.py \
    frontend/tests/test_wf_quickstart_spotify.py \
    -v --tb=short --junitxml=test-results/frontend-wf.xml 2>&1 | tee test-results/frontend-wf.log
  return "${PIPESTATUS[0]}"
}

if [[ "$SUITE" == "core" ]]; then
  run_core || EXIT_CORE=$?
elif [[ "$SUITE" == "frontend" ]]; then
  run_frontend_ui &
  PID1=$!
  run_frontend_features &
  PID2=$!
  run_frontend_wf &
  PID3=$!
  wait "$PID1" || EXIT_FE_UI=$?
  wait "$PID2" || EXIT_FE_FEAT=$?
  wait "$PID3" || EXIT_FE_WF=$?
else
  # Run all 4 groups in parallel
  run_core &
  PID_CORE=$!
  run_frontend_ui &
  PID1=$!
  run_frontend_features &
  PID2=$!
  run_frontend_wf &
  PID3=$!
  wait "$PID_CORE" || EXIT_CORE=$?
  wait "$PID1" || EXIT_FE_UI=$?
  wait "$PID2" || EXIT_FE_FEAT=$?
  wait "$PID3" || EXIT_FE_WF=$?
fi

echo ""
echo "═══════════════════════════════════"
echo "  Test Summary"
echo "═══════════════════════════════════"
if [[ "$SUITE" != "frontend" ]]; then
  [[ $EXIT_CORE -eq 0 ]] && echo "  ✅ Core tests         PASSED" || echo "  ❌ Core tests         FAILED (exit $EXIT_CORE)"
fi
if [[ "$SUITE" != "core" ]]; then
  [[ $EXIT_FE_UI   -eq 0 ]] && echo "  ✅ Frontend UI        PASSED" || echo "  ❌ Frontend UI        FAILED (exit $EXIT_FE_UI)"
  [[ $EXIT_FE_FEAT -eq 0 ]] && echo "  ✅ Features + Onboard PASSED" || echo "  ❌ Features + Onboard FAILED (exit $EXIT_FE_FEAT)"
  [[ $EXIT_FE_WF   -eq 0 ]] && echo "  ✅ Workflow Integr.   PASSED" || echo "  ❌ Workflow Integr.   FAILED (exit $EXIT_FE_WF)"
fi
echo "═══════════════════════════════════"
echo "  XML results in test-results/"
echo "═══════════════════════════════════"

exit $((EXIT_CORE + EXIT_FE_UI + EXIT_FE_FEAT + EXIT_FE_WF))
