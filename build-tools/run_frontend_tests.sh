#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# run_frontend_tests.sh — Run all frontend Playwright tests in parallel
#
# Splits the frontend test suite into 3 parallel groups.
# Each group is a self-contained process with its own Flask server
# and browser instance — no shared state between groups.
#
# Documentation screenshot tests are EXCLUDED by default (they update
# screenshots, not verify behavior). Pass --screenshots to include them.
#
# Usage:
#   bash build-tools/run_frontend_tests.sh                # all frontend tests (no screenshots)
#   bash build-tools/run_frontend_tests.sh --screenshots  # include screenshot tests
#
# Results:  test-results/*.xml  (JUnit XML)
#           test-results/*.log  (console output)
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

INCLUDE_SCREENSHOTS=false
[[ "${1:-}" == "--screenshots" ]] && INCLUDE_SCREENSHOTS=true

EXIT_UI=0
EXIT_FEAT=0
EXIT_WF=0
EXIT_SHOTS=0

mkdir -p test-results

echo "═══════════════════════════════════"
echo "  SpotyVibe Frontend Test Runner"
echo "═══════════════════════════════════"
echo ""

# ── Group 1: UI (page load, navigation, modals) ─────────────
(
  echo "═══ [1/3] Frontend UI (page load, navigation, modals) ═══"
  python -m pytest \
    frontend/tests/test_page_load.py \
    frontend/tests/test_navigation.py \
    frontend/tests/test_modals.py \
    -v --tb=short \
    --junitxml=test-results/frontend-ui.xml
) > >(tee test-results/frontend-ui.log) 2>&1 &
PID_UI=$!

# ── Group 2: Features + Onboarding (profile, generation, edge cases, onboarding) ─
(
  echo "═══ [2/3] Frontend Features + Onboarding ═══"
  python -m pytest \
    frontend/tests/test_profile.py \
    frontend/tests/test_generation.py \
    frontend/tests/test_edge_cases.py \
    frontend/tests/test_onboarding.py \
    frontend/tests/test_profile_integration.py \
    -v --tb=short \
    --junitxml=test-results/frontend-features.xml
) > >(tee test-results/frontend-features.log) 2>&1 &
PID_FEAT=$!

# ── Group 3: Workflow Integration (all workflows) ────────────
(
  echo "═══ [3/3] Workflow Integration ═══"
  python -m pytest \
    frontend/tests/test_wf_onboarding.py \
    frontend/tests/test_wf_generate_create.py \
    frontend/tests/test_wf_generate_append.py \
    frontend/tests/test_wf_generate_override.py \
    frontend/tests/test_wf_analysis.py \
    frontend/tests/test_wf_quickstart_openai.py \
    frontend/tests/test_wf_quickstart_spotify.py \
    -v --tb=short \
    --junitxml=test-results/frontend-wf.xml
) > >(tee test-results/frontend-wf.log) 2>&1 &
PID_WF=$!

# ── Optional: Documentation screenshots ─────────────────────
if [[ "$INCLUDE_SCREENSHOTS" == "true" ]]; then
  (
    echo "═══ [extra] Documentation Screenshots ═══"
    python -m pytest \
      frontend/tests/test_documentation_screenshots.py \
      -v --tb=short -m screenshots \
      --junitxml=test-results/frontend-screenshots.xml
  ) > >(tee test-results/frontend-screenshots.log) 2>&1 &
  PID_SHOTS=$!
fi

# ── Wait for all ─────────────────────────────────────────────
wait "$PID_UI"   || EXIT_UI=$?
wait "$PID_FEAT" || EXIT_FEAT=$?
wait "$PID_WF"   || EXIT_WF=$?
[[ "$INCLUDE_SCREENSHOTS" == "true" ]] && { wait "$PID_SHOTS" || EXIT_SHOTS=$?; }

# ── Summary ──────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════"
echo "  Frontend Test Summary"
echo "═══════════════════════════════════"
[[ $EXIT_UI   -eq 0 ]] && echo "  ✅ UI (page, nav, modals)     PASSED" || echo "  ❌ UI (page, nav, modals)     FAILED (exit $EXIT_UI)"
[[ $EXIT_FEAT -eq 0 ]] && echo "  ✅ Features + Onboarding      PASSED" || echo "  ❌ Features + Onboarding      FAILED (exit $EXIT_FEAT)"
[[ $EXIT_WF   -eq 0 ]] && echo "  ✅ Workflow Integration       PASSED" || echo "  ❌ Workflow Integration       FAILED (exit $EXIT_WF)"
if [[ "$INCLUDE_SCREENSHOTS" == "true" ]]; then
  [[ $EXIT_SHOTS -eq 0 ]] && echo "  ✅ Documentation Screenshots  PASSED" || echo "  ❌ Documentation Screenshots  FAILED (exit $EXIT_SHOTS)"
fi
echo "═══════════════════════════════════"
echo "  XML results in test-results/"
echo "═══════════════════════════════════"

TOTAL=$((EXIT_UI + EXIT_FEAT + EXIT_WF + EXIT_SHOTS))
exit $TOTAL

