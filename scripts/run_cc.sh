#!/usr/bin/env bash
# ── CC Solver: One-command calculus pipeline via Claude Code ─────────────────
# Defaults come from configs/config.yaml. Use flags to override:
#   bash scripts/run_cc.sh                              # use config.yaml defaults
#   bash scripts/run_cc.sh --n 3                        # first 3 problems
#   bash scripts/run_cc.sh --n 5 --K 2                  # first 5, K=2
#   bash scripts/run_cc.sh --id 19_26                   # single problem
#   bash scripts/run_cc.sh --parquet data/raw/xxx.parquet  # custom parquet
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail
cd "$(dirname "$0")/.."

# Parse args — defaults come from configs/config.yaml; only override if specified
N=""
K=""
ID=""
MAX_STEPS=""
MAX_LOOPS=""
WORKERS=""
PARQUET=""

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

# Build command args — only pass non-empty overrides
EXTRA_ARGS=""
[ -n "$N" ]        && EXTRA_ARGS="$EXTRA_ARGS --n $N"
[ -n "$K" ]        && EXTRA_ARGS="$EXTRA_ARGS --K $K"
[ -n "$ID" ]       && EXTRA_ARGS="$EXTRA_ARGS --id $ID"
[ -n "$MAX_STEPS" ] && EXTRA_ARGS="$EXTRA_ARGS --max-steps $MAX_STEPS"
[ -n "$MAX_LOOPS" ] && EXTRA_ARGS="$EXTRA_ARGS --max-loops $MAX_LOOPS"
[ -n "$WORKERS" ]  && EXTRA_ARGS="$EXTRA_ARGS --workers $WORKERS"
[ -n "$PARQUET" ]  && EXTRA_ARGS="$EXTRA_ARGS --parquet $PARQUET"

echo "Running: python scripts/cc_orchestrator.py --parquet $PARQUET $EXTRA_ARGS"
echo ""

source .venv/bin/activate

python scripts/cc_orchestrator.py --parquet "$PARQUET" $EXTRA_ARGS
