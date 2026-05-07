# Multi-Method Calculus Solver (v2)

A **Planner → Builder × K → Evaluator** agent system that solves calculus problems using multiple distinct strategies, verified by SymPy. Built for `qwen-plus` via DashScope (any OpenAI-compatible endpoint works).

> This is a refactored version with CLAUDE.md documentation, improved module separation, and typed configuration. See `CLAUDE.md` for the full architecture guide.

---

## 1. Architecture

```
                 ┌──────────────────────────────────────────┐
                 │  外层循环 outer loop (≤ max_outer_loops) │
                 │  ┌────────────────────────────────────┐  │
 Problem ───────▶│  │  Planner (T=0.9)                   │  │
                 │  │    → K diverse strategies          │  │
                 │  └────────────────────────────────────┘  │
                 │                  │                       │
                 │                  ▼                       │
                 │  ┌────────────────────────────────────┐  │
                 │  │  Builder × K (T=0.2, 并行)          │  │
                 │  │    每个 Builder 跑 ReAct 循环：      │  │
                 │  │      6–12 轮 LLM 调用，每轮决策      │  │
                 │  │      think | tool | finish          │  │
                 │  │    SymPy 执行所有符号运算            │  │
                 │  │    自检：求导/积分互逆校验           │  │
                 │  └────────────────────────────────────┘  │
                 │                  │                       │
                 │                  ▼                       │
                 │  ┌────────────────────────────────────┐  │
                 │  │  Evaluator (T=0.0)                 │  │
                 │  │    五级级联校验：                    │  │
                 │  │      L1 字符串归一                  │  │
                 │  │      L2 符号化简                    │  │
                 │  │      L3 类型专用（积分比导数）       │  │
                 │  │      L4 数值采样（30 点）           │  │
                 │  │      L5 LLM 仲裁（仅当 L1-L4 不确定）│  │
                 │  └────────────────────────────────────┘  │
                 │                  │                       │
                 │  is_correct? ────┴── 否 ──┐              │
                 │      │                    │              │
                 │      是                   ▼              │
                 │      │      记录 failed_strategies        │
                 │      │      → 进入下一轮（带失败提示）    │
                 └──────┼─────────────────────────────────────┘
                        ▼
                  EvalResult + 完整 trace
```

**Key design: Builder ↔ Evaluator loop** — if Evaluator rejects, automatically replan and retry K Builders, up to `max_outer_loops` rounds.

---

## 2. Tech Stack

| Dimension | Choice |
|---|---|
| Python | ≥ 3.10 |
| LLM | `openai` SDK → DashScope OpenAI-compatible endpoint (`qwen-plus`) |
| Data | `pandas`, `pyarrow` (parquet) |
| Symbolic | `sympy` + `latex2sympy2` |
| Async | `asyncio`, `aiohttp` |
| Config | `yaml` + `pydantic` + `pydantic-settings` |
| Testing | `pytest`, `pytest-asyncio` |
| Progress | `tqdm` |

---

## 3. Setup

### Quick: one command

```bash
bash setup.sh
```

This creates a virtual environment, installs dependencies, verifies your `.env` file, runs 50 unit tests, and runs the demo session. If anything is missing or broken, it will tell you exactly what.

### Manual setup

If you prefer to do it yourself:

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # edit with your DASHSCOPE_API_KEY
```

### API Key

Edit `.env`:
```
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Change model in `configs/model.yaml` if needed (e.g. `qwen-max`, `qwen-turbo`).

---

## 4. Usage

### Step 1 — Inspect Data

```bash
python scripts/inspect_parquet.py data/raw/question-v1.parquet
```

### Step 2 — Load + Filter

```bash
python -c "from calc_solver.data.loader import load_parquet; load_parquet('data/raw/question-v1.parquet')"
```

### Step 3 — End-to-End

```bash
# Quick: first 20 problems
python scripts/run_batch.py --parquet data/raw/question-v1.parquet --K 3 --max-rows 20

# Full run
python scripts/run_batch.py --parquet data/raw/question-v1.parquet --K 3
```

### Step 4 — Results

```bash
python scripts/analyze_results.py logs/<run_id>
```

### Step 5 — Tests

```bash
pytest -q
```

### Step 6 — Quick Demo

Run a complete pipeline session with a mock LLM to verify the end-to-end flow:

```bash
python scripts/demo_session.py
```

This runs 5 synthetic calculus problems through Planner → Builder → Evaluator without needing an API key. Use it to validate your setup before a real batch run.

---

## 5. Project Structure

```
calc-solver-v2/
├── CLAUDE.md                          # Root: architecture, conventions, workflow
├── README.md                          # This file
├── pyproject.toml                     # Dependencies
├── Makefile                           # install / test / run
├── configs/                           # YAML configuration
│   ├── config.yaml                    # K, concurrency, retries
│   ├── model.yaml                     # Model id, temperatures
│   └── prompts.yaml                   # All prompts (never hardcode in .py)
│
├── src/calc_solver/
│   ├── CLAUDE.md                      # Package-level documentation
│   ├── schema.py                      # Pydantic data models
│   ├── config/                        # Typed configuration
│   │   ├── __init__.py                # Pydantic config models
│   │   └── settings.py                # YAML loading logic
│   ├── agents/                        # LLM agents
│   │   ├── base.py                    # BaseAgent contract
│   │   ├── planner.py                 # K diverse strategies
│   │   ├── builder.py                 # ReAct loop orchestrator
│   │   ├── builder_loop.py            # _run_loop + message compaction
│   │   ├── builder_self_check.py      # SymPy derivative self-check
│   │   └── evaluator.py               # Evaluation + LLM review
│   ├── data/                          # Data loading
│   │   ├── loader.py                  # Parquet → Problem
│   │   └── normalizer.py              # Text/LaTeX normalization
│   ├── llm/                           # LLM client
│   │   ├── client.py                  # AsyncOpenAI wrapper with retry
│   │   └── prompts.py                 # YAML prompt loader
│   ├── tools/                         # Symbolic tools + verifier
│   │   ├── sympy_tool.py              # diff/integrate/simplify/...
│   │   ├── latex_parser.py            # latex2sympy2 wrapper
│   │   └── verifier/                  # 5-level verification cascade
│   │       ├── base.py               # Orchestration + VerifyResult
│   │       ├── l1_string.py          # String normalization
│   │       ├── l2_symbolic.py        # Symbolic simplification
│   │       ├── l3_type_specific.py   # Type-specific checks
│   │       ├── l4_numerical.py       # Numerical sampling
│   │       └── l5_llm.py             # LLM arbitration
│   ├── orchestrator/                  # Pipeline orchestration
│   │   └── pipeline.py                # solve_one + run_batch
│   └── utils/                         # Utilities
│       ├── logger.py                  # JSONL structured logging
│       └── ids.py                     # Run ID generation
│
├── scripts/
│   ├── run_batch.py                   # Batch runner entry point
│   ├── demo_session.py                # Mock/real session demo
│   ├── analyze_results.py             # Result summarization
│   └── inspect_parquet.py             # Data exploration
│
└── tests/
    └── ...                            # 50+ tests
```

---

## 6. Key Configuration

| Section | Setting | Default | Description |
|---|---|---|---|
| `run` | `K` | 3 | Planner strategy count |
| `run` | `max_outer_loops` | 2 | Builder↔Evaluator retry rounds |
| `run` | `builder_max_steps` | 12 | Max LLM turns per Builder |
| `run` | `builder_max_retries` | 2 | Self-check retry count |
| `run` | `problem_concurrency` | 4 | Parallel problems |
| `run` | `builder_concurrency_per_problem` | 3 | Parallel Builders per problem |
| `rate_limits` | `max_concurrent_llm_calls` | 16 | Global LLM concurrency |
| `verifier` | `n_samples` | 30 | L4 numerical sampling points |

---

## 7. Five-Level Verifier

| Level | Method | Applies To | Confidence |
|---|---|---|---|
| L1 | String normalization | Exact match | 1.0 |
| L2 | Symbolic simplification | Expressions | 0.95 |
| L3 | Type-specific (derivative compare for indefinite integrals) | By answer_type | 0.95 |
| L4 | Numerical sampling (30 points) | Expressions/values | 0.9 |
| L5 | LLM arbitration (only when L1-L4 inconclusive + ≥50% pass) | Edge cases | 0.6 |

**L1-L4 all fail → False immediately, no LLM call** (avoids LLM washing wrong answers into correct). `is_correct` can only be flipped True by Verifier; LLM "full review" only writes to `notes`.

---

## 7b. Anti-Cheating: Gold Answer Isolation

Solving agents (Planner, Builder) **cannot** access `gold_answer`. This is enforced at the
type level, not by convention:

| Layer | Mechanism | Details |
|---|---|---|
| Type system | `SolvingProblem` has NO `gold_answer` field | `schema.py` |
| Type signatures | `PlannerAgent.plan(problem: SolvingProblem)` | Python will reject `Problem` |
| Single strip point | `SolvingProblem.from_problem(p)` in `Pipeline.solve_one()` | One line, auditable |
| Tests | Verify type annotations + prompt scan | `tests/test_no_cheating.py` |

```
Pipeline.solve_one(problem: Problem):
    solving = SolvingProblem.from_problem(problem)  ← ONLY place gold is stripped
    self.planner.plan(solving)    # type: SolvingProblem — no gold exists
    self.builder.build(solving)   # type: SolvingProblem — no gold exists
    self.evaluator.evaluate(problem, ...)  # type: Problem — needs gold for grading
```

Evaluator and Verifier receive the full `Problem` because they are the grader.
Self-check verifies indefinite integrals by differentiation, not by comparing to gold.

---

## 8. Data Format

| Column | Type | Description |
|---|---|---|
| `id` | str | Unique problem ID |
| `source` | str | Source identifier |
| `question` | str | Problem text (LaTeX) |
| `answer` | str | Standard answer (LaTeX or value) |
| `solution` | str | Reference solution (not consumed by system) |
| `tag` | dict | `problem_type / have_definite / have_indefinite / ...` |
| `reference` | list | Reference materials |

Loader auto-maps column names. See `configs/config.yaml` `data.column_overrides` for manual overrides.

---

## 9. Troubleshooting

| Issue | Solution |
|---|---|
| `latex2sympy2` install fails | Use `pip install latex2sympy2>=1.9.0` |
| Column mapping fails | Run `inspect_parquet.py`, fill `data.column_overrides` |
| API rate limited | Reduce `max_concurrent_llm_calls` and `problem_concurrency` |
| Interrupted run | Re-run same `--run-id`, existing problems auto-skip |

## License

MIT
