#!/usr/bin/env bash
# ── CC Solver: One-command calculus pipeline via Claude Code ─────────────────
# Usage:
#   bash scripts/run_cc.sh                              # all problems, K=3, 3 workers
#   bash scripts/run_cc.sh --n 3                        # first 3 problems
#   bash scripts/run_cc.sh --n 5 --K 2                  # first 5, K=2 strategies
#   bash scripts/run_cc.sh --n 10 --workers 5           # 10 problems, 5 parallel workers
#   bash scripts/run_cc.sh --id 19_26                   # single problem by ID
#   bash scripts/run_cc.sh --parquet data/raw/xxx.parquet  # custom parquet file
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail
cd "$(dirname "$0")/.."

# Parse args
N=""
K="3"
ID=""
MAX_STEPS="12"
MAX_LOOPS="3"
WORKERS="3"
PARQUET="question_filtered_example.parquet"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --n)        N="$2"; shift 2;;
    --K)        K="$2"; shift 2;;
    --id)       ID="$2"; shift 2;;
    --max-steps) MAX_STEPS="$2"; shift 2;;
    --max-loops) MAX_LOOPS="$2"; shift 2;;
    --workers)  WORKERS="$2"; shift 2;;
    --parquet)  PARQUET="$2"; shift 2;;
    *)          echo "Unknown option: $1"; exit 1;;
  esac
done

# Build command args
EXTRA_ARGS=""
[ -n "$N" ]        && EXTRA_ARGS="$EXTRA_ARGS --n $N"
[ -n "$ID" ]       && EXTRA_ARGS="$EXTRA_ARGS --id $ID"
EXTRA_ARGS="$EXTRA_ARGS --K $K"
EXTRA_ARGS="$EXTRA_ARGS --max-steps $MAX_STEPS"
EXTRA_ARGS="$EXTRA_ARGS --max-loops $MAX_LOOPS"
EXTRA_ARGS="$EXTRA_ARGS --workers $WORKERS"

echo "Running: python scripts/cc_orchestrator.py --parquet $PARQUET $EXTRA_ARGS"
echo ""

source .venv/bin/activate

python scripts/cc_orchestrator.py --parquet "$PARQUET" $EXTRA_ARGS
