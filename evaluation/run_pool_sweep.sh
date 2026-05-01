#!/usr/bin/env bash
# WARNING: do NOT edit this script while a sweep is running. Bash re-reads
# the file on loop exit; line-offset shifts cause "syntax error near unexpected
# token" failures during post-processing. Apply edits between sweeps only.
#
# evaluation/run_pool_sweep.sh — End-to-end pool-size sweep driver.
#
# What it does:
#   1. For each (block, pool_size) in the configured sequence:
#        a. Wait COOLDOWN seconds (Spotify rate-limit safety).
#        b. Patch config.py to set RETRIEVE_CANDIDATES_SIZE = <pool>.
#        c. Run the standard eval harness (`python evaluation/run_evaluation.py`).
#        d. Scan the run log for Spotify 429 errors. If found → abort the
#           remaining sweep cleanly so we don't burn money on rate-limited runs.
#   2. After all runs (or on early abort), aggregate every run's eval.jsonl into
#      a single CSV and render a markdown comparison report.
#
# Output (everything ends up under evaluation/results/sweep-<UTC-timestamp>/):
#   - manifest.tsv          (block, pool, run_dir, start, end, status, n_429)
#   - sweep.log             (high-level sweep timeline)
#   - run_<pool>_b<block>.log   (per-eval stdout/stderr — large, full debug)
#   - summary.csv           (one row per (block, pool, model))
#   - report.md             (human-readable comparison)
#
# After the sweep, point any agent (or open the file yourself) at
#   <SWEEP_DIR>/report.md     — high-level findings
#   <SWEEP_DIR>/summary.csv   — raw numbers for further analysis
#   <SWEEP_DIR>/manifest.tsv  — pointers to per-run eval.jsonl files
#
# Usage:
#   bash evaluation/run_pool_sweep.sh                 # default sweep
#   COOLDOWN=180 bash evaluation/run_pool_sweep.sh    # shorter cooldown (use with care)
#   POOLS="30 50" BLOCKS=3 bash evaluation/run_pool_sweep.sh   # custom sequence
#
#   # Resume after a partial sweep — e.g., block 1 done, block 2 only had
#   # pool 30 done, blocks 3-5 still pending. Run blocks 2-5 where block 2
#   # only fills the missing pools (40, 50):
#   START_BLOCK=2 BLOCKS=5 FIRST_BLOCK_POOLS="40 50" \
#       bash evaluation/run_pool_sweep.sh
#
# Exit codes:
#   0 — sweep complete, all runs OK
#   1 — sweep aborted due to Spotify 429 cascade
#   2 — sweep aborted due to a non-rate-limit failure (eval crashed)

set -u
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

# ── Configuration (env-overridable) ──────────────────────────────────────────
COOLDOWN="${COOLDOWN:-480}"                # seconds between runs (8 min default)
POOLS="${POOLS:-30 40 50}"                 # space-separated pool sizes
BLOCKS="${BLOCKS:-2}"                      # last block number to run (inclusive)
START_BLOCK="${START_BLOCK:-1}"            # first block number to run (resume support)
FIRST_BLOCK_POOLS="${FIRST_BLOCK_POOLS:-}" # if set, override POOLS for the *first* block only
                                           # (used when resuming a partially-completed block)
RATE_LIMIT_THRESHOLD="${RATE_LIMIT_THRESHOLD:-3}"   # >= this many 429s in one run → abort

SWEEP_TS="$(date -u +%Y%m%dT%H%M%SZ)"
SWEEP_DIR="$ROOT/evaluation/results/sweep-$SWEEP_TS"
LOG="$SWEEP_DIR/sweep.log"
MANIFEST="$SWEEP_DIR/manifest.tsv"
SUMMARY_CSV="$SWEEP_DIR/summary.csv"
REPORT_MD="$SWEEP_DIR/report.md"

mkdir -p "$SWEEP_DIR"
: > "$LOG"
echo -e "block\tpool\trun_dir\tstart\tend\tstatus\tn_429" > "$MANIFEST"

# ── Helpers ─────────────────────────────────────────────────────────────────
log() {
    # Print to stdout AND the sweep log, with a wall-clock prefix.
    local msg="[$(date +%H:%M:%S)] $*"
    echo "$msg" | tee -a "$LOG"
}

set_pool() {
    # Patch config.py so the next eval invocation picks up the new pool size.
    # Idempotent: if the file already declares the requested value, log and
    # return success rather than raising "no replacement made" — the previous
    # sweep run may have left it in the desired state.
    local pool=$1
    local out
    out=$(python -c "
import re, sys, pathlib
p = pathlib.Path('config.py')
src = p.read_text(encoding='utf-8')
m = re.search(r'^RETRIEVE_CANDIDATES_SIZE = (\d+)', src, flags=re.M)
if not m:
    print('ERROR: RETRIEVE_CANDIDATES_SIZE line not found in config.py', file=sys.stderr)
    sys.exit(1)
current = int(m.group(1))
if current == $pool:
    print(f'config.py: RETRIEVE_CANDIDATES_SIZE already = $pool (no change needed)')
    sys.exit(0)
new = re.sub(r'^RETRIEVE_CANDIDATES_SIZE = \d+',
             'RETRIEVE_CANDIDATES_SIZE = $pool', src, count=1, flags=re.M)
p.write_text(new, encoding='utf-8')
print(f'config.py: RETRIEVE_CANDIDATES_SIZE = $pool (was {current})')
" 2>&1)
    local rc=$?
    # Mirror python output to terminal AND log, but preserve python's exit
    # code (a `tee` pipe would have masked it as 0 — that was the original bug).
    echo "$out" | tee -a "$LOG"
    return $rc
}

count_rate_limits() {
    # Count distinct 429 hits in a per-run log. Used to detect the start of a
    # rate-limit cascade. We grep for the spotipy error signature, which
    # appears once per failed search.
    # `grep -c` always prints a count (0 if no matches) but exits 1 when the
    # count is zero. The previous `|| echo 0` therefore appended a *second* "0"
    # line on the no-match path, producing multi-line output like "0\n0" that
    # broke the `[ "$n_429" -ge ... ]` integer test downstream. Swallow the
    # exit code with `|| true` so the single number grep already printed is
    # the only thing we emit.
    local run_log=$1
    grep -c "Too many requests" "$run_log" 2>/dev/null || true
}

# ── User-facing banner ──────────────────────────────────────────────────────
log "════════════════════════════════════════════════════════════════════"
log " Pool-size sweep starting"
log "   Pools     : $POOLS"
log "   Blocks    : $START_BLOCK..$BLOCKS"
if [ -n "$FIRST_BLOCK_POOLS" ]; then
    log "   First-block pool override: $FIRST_BLOCK_POOLS (only block $START_BLOCK)"
fi
log "   Cooldown  : ${COOLDOWN}s between runs"
log "   429 abort : if any single run logs >= $RATE_LIMIT_THRESHOLD '429' errors"
log "   Output    : $SWEEP_DIR"
log "════════════════════════════════════════════════════════════════════"

TOTAL_RUNS=0
SWEEP_STATUS="ok"

# Pre-compute total planned runs so the abort message is accurate even when
# FIRST_BLOCK_POOLS overrides the first block's pool list.
n_pools_default=$(echo $POOLS | wc -w)
n_blocks_total=$((BLOCKS - START_BLOCK + 1))
if [ -n "$FIRST_BLOCK_POOLS" ]; then
    n_first=$(echo $FIRST_BLOCK_POOLS | wc -w)
    PLANNED_RUNS=$((n_first + (n_blocks_total - 1) * n_pools_default))
else
    PLANNED_RUNS=$((n_blocks_total * n_pools_default))
fi

for block in $(seq "$START_BLOCK" "$BLOCKS"); do
    # On the first block of a resumed sweep, the user can override which pools
    # run (e.g., to fill in just the cells that were missing from a prior run).
    if [ "$block" = "$START_BLOCK" ] && [ -n "$FIRST_BLOCK_POOLS" ]; then
        block_pools="$FIRST_BLOCK_POOLS"
    else
        block_pools="$POOLS"
    fi
    for pool in $block_pools; do
        TOTAL_RUNS=$((TOTAL_RUNS+1))

        # ── Cooldown ────────────────────────────────────────────────────
        log "── block=$block pool=$pool: waiting ${COOLDOWN}s for Spotify cooldown ──"
        sleep "$COOLDOWN"

        # ── Set pool size ──────────────────────────────────────────────
        if ! set_pool "$pool"; then
            log "❌ Failed to patch config.py for pool=$pool — aborting."
            SWEEP_STATUS="config_patch_failed"; break 2
        fi

        # ── Run eval ───────────────────────────────────────────────────
        run_log="$SWEEP_DIR/run_p${pool}_b${block}.log"
        start_ts=$(date -u +%Y%m%dT%H%M%SZ)
        log "▶ block=$block pool=$pool: starting eval at $start_ts"

        if python evaluation/run_evaluation.py --no-confirm > "$run_log" 2>&1; then
            run_status="ok"
        else
            run_status="failed"
        fi
        end_ts=$(date -u +%Y%m%dT%H%M%SZ)

        # ── Discover the run directory the harness just created ────────
        run_dir=$(ls -td "$ROOT"/evaluation/results/2026* 2>/dev/null \
                    | grep -v "/sweep-" | head -1)
        run_dir_name=$(basename "$run_dir")

        # ── 429 detection ──────────────────────────────────────────────
        n_429=$(count_rate_limits "$run_log")
        echo -e "$block\t$pool\t$run_dir_name\t$start_ts\t$end_ts\t$run_status\t$n_429" \
            >> "$MANIFEST"

        log "  done: status=$run_status, run_dir=$run_dir_name, 429_hits=$n_429"

        if [ "$n_429" -ge "$RATE_LIMIT_THRESHOLD" ]; then
            log ""
            log "🛑 ════════════════════════════════════════════════════════════════"
            log "🛑  ABORTING SWEEP — Spotify rate limit detected"
            log "🛑    block=$block pool=$pool produced $n_429 '429 Too many requests' errors"
            log "🛑    (threshold = $RATE_LIMIT_THRESHOLD)"
            log "🛑"
            log "🛑  $((TOTAL_RUNS-1)) of $PLANNED_RUNS planned runs completed before abort."
            log "🛑  Wait at least 30 minutes before re-starting the sweep."
            log "🛑  The partial results so far are still aggregated below."
            log "🛑 ════════════════════════════════════════════════════════════════"
            SWEEP_STATUS="aborted_rate_limit"
            break 2
        fi

        if [ "$run_status" = "failed" ]; then
            log ""
            log "🛑 ════════════════════════════════════════════════════════════════"
            log "🛑  ABORTING SWEEP — eval run crashed (non-rate-limit failure)"
            log "🛑    See: $run_log"
            log "🛑 ════════════════════════════════════════════════════════════════"
            SWEEP_STATUS="aborted_eval_failed"
            break 2
        fi
    done
done

# ── Post-processing: aggregate + report ─────────────────────────────────────
log ""
log "════════════════════════════════════════════════════════════════════"
log " Sweep finished (status=$SWEEP_STATUS). Aggregating results…"
log "════════════════════════════════════════════════════════════════════"

# Aggregator: writes summary.csv into the sweep dir.
if python evaluation/_aggregate_sweep.py "$MANIFEST" "$SUMMARY_CSV" 2>&1 | tee -a "$LOG"; then
    log "✅ Wrote $SUMMARY_CSV"
else
    log "⚠ Aggregator failed — see log above. Per-run eval.jsonl files are still intact."
fi

# Report renderer: writes report.md into the sweep dir.
if python evaluation/_render_sweep_report.py "$SUMMARY_CSV" "$REPORT_MD" 2>&1 | tee -a "$LOG"; then
    log "✅ Wrote $REPORT_MD"
else
    log "⚠ Report rendering failed — summary.csv is still available."
fi

log ""
log "════════════════════════════════════════════════════════════════════"
log " Done. Inspect:"
log "   $REPORT_MD"
log "   $SUMMARY_CSV"
log "   $MANIFEST"
log "════════════════════════════════════════════════════════════════════"

# Exit code reflects sweep status.
case "$SWEEP_STATUS" in
    ok)                   exit 0 ;;
    aborted_rate_limit)   exit 1 ;;
    *)                    exit 2 ;;
esac

