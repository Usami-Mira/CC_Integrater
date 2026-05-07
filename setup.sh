#!/usr/bin/env bash
set -euo pipefail

# ── calc-solver-v2: Setup Script ─────────────────────────────────────────────
# Usage:  bash setup.sh
#         Creates venv, installs deps, verifies .env, runs smoke tests.
# ─────────────────────────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
SEP="────────────────────────────────────────"

info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
fail()  { echo -e "${RED}[✗]${NC} $1" >&2; exit 1; }
step()  { echo -e "\n${SEP}"; echo "  $1"; echo "$SEP"; }

cd "$(dirname "$0")"

# ── 1. Python version ────────────────────────────────────────────────────────
step "Checking Python"
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null \
  || fail "Python ≥ 3.10 required (found: $(python3 --version 2>&1 || echo 'none'))"
PY_VER=$(python3 --version 2>&1)
info "Found $PY_VER"

# ── 2. Virtual environment ───────────────────────────────────────────────────
step "Setting up virtual environment"
if [ -d ".venv" ]; then
  warn ".venv exists, reusing"
else
  python3 -m venv .venv
  info "Created .venv"
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# ── 3. Install dependencies ──────────────────────────────────────────────────
step "Installing dependencies"
pip install -q -e ".[dev]" 2>&1 | tail -3
info "Installed all packages"

# ── 4. Environment file ──────────────────────────────────────────────────────
step "Checking environment"
if [ -f ".env" ]; then
  if grep -q 'sk-8522a2ac103440e0b57f5cf1c9ef6ff2' .env 2>/dev/null; then
    warn ".env contains the placeholder/example key — edit it with your real DASHSCOPE_API_KEY"
  elif grep -q 'sk-xxxx\|sk-xxxxxxxx' .env 2>/dev/null; then
    fail ".env still has placeholder key. Edit .env and set DASHSCOPE_API_KEY."
  else
    info ".env loaded"
  fi
else
  warn ".env not found, copying from .env.example"
  cp .env.example .env
  fail "Edit .env with your DASHSCOPE_API_KEY and re-run this script"
fi

# ── 5. Data check ────────────────────────────────────────────────────────────
step "Checking data files"
if [ -f "data/raw/synth-v1.parquet" ]; then
  info "data/raw/synth-v1.parquet exists ($(wc -c < data/raw/synth-v1.parquet) bytes)"
else
  warn "data/raw/synth-v1.parquet not found — real-data runs need a parquet file"
fi

# ── 6. Smoke tests ───────────────────────────────────────────────────────────
step "Running smoke tests (50 unit tests, no API)"
pytest -q 2>&1 | tail -5
info "Tests passed"

# ── 7. Demo session ─────────────────────────────────────────────────────────
step "Running demo session (mock LLM, end-to-end pipeline)"
python scripts/demo_session.py 2>&1 | tail -15
info "Demo completed"

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "${SEP}"
echo -e "  ${GREEN}Setup complete${NC}"
echo "${SEP}"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your real DASHSCOPE_API_KEY (if not already done)"
echo "  2. Place your parquet files in data/raw/"
echo "  3. Quick run:  python scripts/run_batch.py --parquet data/raw/synth-v1.parquet --K 3 --max-rows 10"
echo "  4. Full run:   python scripts/run_batch.py --parquet data/raw/synth-v1.parquet --K 3"
echo ""
echo "Activate env:    source .venv/bin/activate"
echo "Run tests:       pytest -q"
echo ""
