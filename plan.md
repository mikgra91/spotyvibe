# SpotyVibe — Test Parallelization & Containerization Plan (2026-04-15)

> **Goal.** Fix the conftest conflict, speed up the test suite, and provide both a lightweight parallel runner (daily dev) and a Podman-based runner (CI / heavy testing).

---

## Current Test Performance

| Suite | Tests | Runtime | Type |
|---|---|---|---|
| `core/tests/` | 458 | ~3.5s | Unit tests (pure Python, mocked APIs) |
| `frontend/tests/` | 237 | ~5-8 min | Playwright browser tests (Chromium) |
| **Total** | **695** | **~5-8 min** | **Can't even run together (conftest conflict)** |

---

## Analysis: Podman Containers?

Podman containers would help, but there's a simpler first step:

- **Core tests (3.5s)** — Already blazing fast. Containerization adds startup overhead that would make them slower.
- **Frontend tests (5-8 min)** — These are the bottleneck. Each Playwright test launches a browser, loads ~60 static assets, and uses `wait_for_timeout()` calls. Containers help with isolation but don't speed up browser interaction.
- **Conftest conflict** — The `ImportPathMismatchError` prevents running both suites in one `pytest` invocation. This is a packaging issue, not a parallelization issue.

---

## Proposed Plan (2 phases)

### Phase 1: Parallel test runner script (no containers)

1. Fix the conftest conflict so both suites can coexist.
2. Create a `run_tests.sh` script that runs core and frontend tests in parallel using background processes.
3. Add `pytest-xdist` for frontend tests to split them across N workers (`-n auto`).
4. **Expected speedup:** ~2-3× for frontend tests (Playwright supports parallel workers).

### Phase 2: Podman container test runner

1. Create a `Dockerfile.test` with Python + Playwright + Chromium.
2. Create a `run_tests_podman.sh` script that:
   - Builds the test image once.
   - Spins up 3 parallel containers: core tests, frontend-1 (`test_frontend.py`), frontend-2 (`test_profile_integration.py` + `test_workflow_integration.py`).
   - Collects JUnit XML results from each container.
   - Prints a unified pass/fail summary.
3. This gives full isolation + parallel execution + CI-ready output.

---

## Files to create/modify

| File | Action | Purpose |
|---|---|---|
| `Dockerfile.test` | Create | Test container image |
| `build-tools/run_tests.sh` | Create | Simple parallel runner (no containers) |
| `build-tools/run_tests_podman.sh` | Create | Podman-based parallel runner |
| `requirements.txt` | Modify | Add `pytest-xdist` |
| `pytest.ini` | Modify | Fix import mode for conftest conflict |
| `core/tests/conftest.py` | Modify | Fix namespace collision |
| `frontend/tests/conftest.py` | Modify | Fix namespace collision |

