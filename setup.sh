#!/usr/bin/env bash
set -euo pipefail

# ── CC-Integrater: Setup Script ──────────────────────────────────────────────
# Usage:  bash setup.sh
#         Creates venv, installs deps, verifies setup, runs smoke test.
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
info "Found $(python3 --version 2>&1)"

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
pip install --upgrade pip -q
pip install \
  pandas \
  pyarrow \
  sympy \
  pyyaml \
  numpy \
  latex2sympy2 \
  python-dotenv \
  tqdm \
  pytest \
  -q
info "Installed: pandas, pyarrow, sympy, pyyaml, numpy, latex2sympy2, tqdm, pytest"

# ── 4. Verify core imports ───────────────────────────────────────────────────
step "Verifying core imports"
python -c "
import pandas
import pyarrow
import sympy
import yaml
import numpy
import latex2sympy2
print('  pandas   ', pandas.__version__)
print('  sympy    ', sympy.__version__)
print('  pyyaml   ', yaml.__version__)
print('  numpy    ', numpy.__version__)
print('  latex2sympy2 loaded')
" || fail "Import check failed"
info "All core imports OK"

# ── 5. Claude Code ───────────────────────────────────────────────────────────
step "Checking Claude Code"
if command -v claude &>/dev/null; then
  info "Claude Code found: $(claude --version 2>/dev/null || echo 'installed')"
else
  warn "claude not in PATH — CC --print mode requires: npm install -g @anthropic-ai/claude-code"
fi

# ── 6. Data check ────────────────────────────────────────────────────────────
step "Checking data files"
PARQUET=$(find . -maxdepth 2 -name "*.parquet" ! -path "./.venv/*" 2>/dev/null | head -1)
if [ -n "$PARQUET" ]; then
  info "Parquet file found: $PARQUET ($(wc -c < "$PARQUET") bytes)"
else
  warn "No .parquet files found — put your data in the project root or data/raw/"
fi

# ── 7. Quick smoke test ──────────────────────────────────────────────────────
step "Running smoke test (SymPy tools + Verifier)"
python scripts/cc_sympy.py integrate_indef "x**2" && \
python scripts/cc_sympy.py simplify "sin(x)**2 + cos(x)**2" && \
python scripts/cc_sympy.py differentiate "sin(x)" || fail "SymPy tools failed"
info "Smoke test passed"

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "${SEP}"
echo -e "  ${GREEN}Setup complete${NC}"
echo "${SEP}"
echo ""
echo "Next steps:"
echo "  Activate env:  source .venv/bin/activate"
echo "  Quick run:     bash scripts/run_cc.sh --id 19_15"
echo "  Batch run:     bash scripts/run_cc.sh --n 10 --K 3 --workers 3"
echo "  Tests:         pytest -q"
echo ""
