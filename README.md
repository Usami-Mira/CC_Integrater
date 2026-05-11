# CC-Integrater — Multi-Method Calculus Solver

A **Planner → Builder × K → Evaluator** agent system that solves calculus problems using multiple distinct strategies, verified by SymPy. Runs via **Claude Code** (`--print` mode) instead of external LLM APIs.

```
bash scripts/run_cc.sh              # all problems
bash scripts/run_cc.sh --n 3        # first 3
bash scripts/run_cc.sh --id 19_26   # single problem
```

---

## 1. Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  cc_orchestrator.py (Python, runs OUTSIDE Claude context)             │
│  ┌─ gold_answer lives ONLY here ───────────────────────────────────┐ │
│  │                                                                  │ │
│  ▼                                                                  │ │
│  Planner (CC --print)          ← sees: question only                │ │
│    └──▶ K strategies                                                │ │
│         │                                                            │ │
│         ├──▶ Builder (CC --print) ← sees: question + strategy only  │ │
│         │      │                                                     │ │
│         │      ▼                                                     │ │
│         │  Evaluator (CC --print) ← sees: question + answer + bool  │ │
│         │      │                   ← NEVER sees gold_answer         │ │
│         │      ▼                                                     │ │
│         │  Verifier (pure Python) ← gold stays HERE, returns bool   │ │
│         │      │                                                     │ │
│         │      ├── True ──▶ record, try next strategy               │ │
│         │      └── False ──▶ Builder retry (×2 per strategy)        │ │
│         │                                                            │ │
│         ├──▶ ... (K strategies, all run regardless)                  │ │
│         │                                                            │ │
│         └──▶ ... (replan if none succeeded, max 3 outer loops)       │ │
│                                                                      │ │
│  └─▶ Trace output: narrative MD solution + JSON trace per problem    │ │
└──────────────────────────────────────────────────────────────────────┘
```

### Execution model

| Agent | How it runs | Sees gold? |
|---|---|---|
| Orchestrator (Python) | Python process | YES — only place gold exists |
| Planner | `claude --print --dangerously-skip-permissions` | NO |
| Builder (×K) | `claude --print --dangerously-skip-permissions` | NO |
| Evaluator | `claude --print --dangerously-skip-permissions` | NO — only gets Verifier's boolean |
| Verifier | Pure Python (`asyncio` + SymPy) | YES — runs in Python, no Claude |

### Gold answer isolation

Gold answers exist **only** in the Python orchestrator's memory. They are passed to `run_verifier()` (pure Python), which returns a boolean. The Evaluator receives only `true`/`false` — no gold expression, no verification details. This is a **data-level** guarantee, not type-level.

---

## 2. Workflow

1. **Planner** generates K distinct solving strategies as JSON
2. **Each strategy** goes through a Builder → Evaluator cycle:
   - Builder calls SymPy CLI tools step by step, produces a final answer
   - Verifier checks against gold (Python, L1-L4 cascade)
   - Evaluator receives only the boolean verdict, decides whether to retry
   - If Verifier says correct → record, move to next strategy
   - If Verifier says wrong + Evaluator says retry → Builder tries again
3. **All K strategies run** — even if earlier ones succeed (for comparison)
4. **If none succeeded** → replan with different methods (max 3 outer loops)
5. **Trace output** — each strategy's full solving process rendered as narrative math solution

---

## 3. Tech Stack

| Dimension | Choice |
|---|---|
| Python | ≥ 3.10 |
| LLM | Claude Code `--print` mode (headless) |
| Data | `pandas`, `pyarrow` (parquet) |
| Symbolic | `sympy` + `latex2sympy2` |
| Config | `yaml` |
| Testing | `pytest` |

---

## 4. Setup

### Quick: one command

```bash
bash setup.sh
```

Creates virtual environment, installs dependencies, verifies `.env`, runs tests.

### Manual

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # edit with your API key
```

### API Key

Edit `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
```

---

## 5. Usage

### Run the full pipeline

```bash
bash scripts/run_cc.sh              # all problems
bash scripts/run_cc.sh --n 3        # first 3 problems
bash scripts/run_cc.sh --id 19_26   # single problem
bash scripts/run_cc.sh --K 5        # 5 strategies per problem
```

### Direct orchestrator

```bash
.venv/bin/python scripts/cc_orchestrator.py \
    --parquet question_filtered_example.parquet \
    --K 3 --n 5 --max-loops 3
```

---

## 6. Logging

All runs produce timestamped logs under `logs/cc/YYYYMMDD_HHMMSS/`:

```
logs/cc/20260511_174735/
├── output.log              # Full terminal output (timestamped)
├── planner_output.log      # Planner CC raw output
├── builder_1_output.log    # Builder attempt 1 raw output
├── evaluator_output.log    # Evaluator CC raw output
├── traces/
│   ├── 19_15.md            # Human-readable solution narrative
│   ├── 19_15.json          # Machine-readable full trace
│   ├── 19_26.md            # All K strategies shown as step-by-step
│   └── 19_26.json          # solutions with tool calls and results
├── summary.json            # Batch statistics
└── summary.md              # Human-readable accuracy report
```

### Trace format (Markdown)

Each `.md` trace is a **standard math solution** — narrative prose with step-by-step working, like a textbook answer:

```
# 19_26

**题目** 19.26 Evaluate ∫ x/√(x+1) dx

**标准答案** 2/3 √(x+1)(x-2) + C

**状态** ✅ 正确

## 解题过程

### 方法 u-substitution (algebraic)（第 1 次尝试）— ✅ 通过

Step 1：对 u^(1/2) - u^(-1/2) 关于 u 积分
得 2u^(3/2)/3 - 2√u

Step 2：代入 u=x+1
得 2(x-2)√(x+1)/3

Step 3：求导验证
得 x/√(x+1)

**结果**  $$ 2/3 (x-2)√(x+1) + C $$

验证：symbolic_simplify（L2）
---

### 方法 Integration by parts（第 1 次尝试）— ✅ 通过
...
---

## 最终结果
$$ 2/3 (x-2)√(x+1) + C $$

最佳方法：u-substitution (algebraic)
```

### View results

```bash
python scripts/cc_summary.py --latest
python scripts/cc_summary.py logs/cc/20260511_174735
cat logs/cc/20260511_174735/traces/19_26.md
```

---

## 7. SymPy Tools

All computation goes through `scripts/cc_sympy.py`, called via Bash:

```bash
python scripts/cc_sympy.py integrate_indef "expr" [var]
python scripts/cc_sympy.py integrate_def "expr" var "a" "b"
python scripts/cc_sympy.py differentiate "expr" [var] [n]
python scripts/cc_sympy.py simplify "expr"
python scripts/cc_sympy.py parse "expr" [var]
python scripts/cc_sympy.py solve "expr" [var]
python scripts/cc_sympy.py limit "expr" var "point" [dir]
python scripts/cc_sympy.py series "expr" var "point" [n]
python scripts/cc_sympy.py substitute "expr" "mapping"
```

All output: `{"ok": true, "result": "...", "error": null}`

---

## 8. Five-Level Verifier

| Level | Method | Applies To | Confidence |
|---|---|---|---|
| L1 | String normalization | Exact match | 1.0 |
| L2 | Symbolic simplification | Expressions | 0.95 |
| L3 | Type-specific (derivative compare) | By answer_type | 0.95 |
| L4 | Numerical sampling (30 points) | Expressions/values | 0.9 |
| L5 | LLM arbitration (blind P vs G) | Edge cases | 0.6 |

L1-L4 all fail → False immediately, no LLM call. The orchestrator can invoke L5 separately when needed.

---

## 9. Strategy Methods

- **不定积分**: 基本公式 / 凑微分 / 分部积分 / 三角换元 / 万能代换 / 部分分式
- **定积分**: 上述 + 对称性 / King's rule / Feynman
- **极限**: 洛必达 / 泰勒 / 夹逼 / 代换
- **求导**: 链式 / 隐函数 / 对数求导

---

## 10. Configuration

| Parameter | Default | Description |
|---|---|---|
| `--K` | 3 | Number of solving strategies per problem |
| `--max-loops` | 3 | Max outer replanning loops |
| `--max-steps` | 12 | Max steps per Builder attempt (enforced by CC) |
| `--n` | all | Max problems to process |
| `--id` | - | Specific problem ID to run |
| `--parquet` | `question_filtered_example.parquet` | Input data file |

---

## 11. Project Structure

```
CC-Integrater/
├── CLAUDE.md                          # Architecture & conventions
├── README.md                          # This file
├── pyproject.toml                     # Dependencies
├── configs/
│   ├── config.yaml                    # Pipeline settings (K, loops, etc.)
│   ├── model.yaml                     # Model configuration
│   └── prompts.yaml                   # All prompt templates
│
├── scripts/
│   ├── run_cc.sh                      # Entry point — runs full pipeline
│   ├── cc_orchestrator.py             # Main orchestrator (Planner→Builder→Evaluator)
│   ├── cc_sympy.py                    # SymPy tool CLI
│   ├── cc_verify.py                   # Verifier CLI (L1-L4, pure Python)
│   ├── cc_load.py                     # Parquet → JSON problem loader
│   ├── cc_prompt_builder.py           # Prompt assembler from YAML
│   ├── cc_summary.py                  # Summary report generator
│   ├── run_batch.py                   # Original API-based batch runner
│   ├── demo_session.py                # Mock pipeline demo
│   ├── analyze_results.py             # Legacy result analyzer
│   └── inspect_parquet.py             # Data exploration
│
├── src/calc_solver/                   # Original Python solver library
│   ├── schema.py                      # Data models
│   ├── agents/                        # LLM agents (original API-based)
│   ├── tools/verifier/                # 5-level verification cascade
│   └── ...                            # Config, utils, etc.
│
└── logs/cc/                           # Timestamped run logs
    └── YYYYMMDD_HHMMSS/
        ├── output.log
        ├── planner_output.log
        ├── builder_*_output.log
        ├── evaluator_output.log
        ├── traces/*.md                # Human-readable solutions
        ├── traces/*.json              # Machine-readable traces
        ├── summary.md                 # Accuracy report
        └── summary.json
```

---

## 12. Troubleshooting

| Issue | Solution |
|---|---|
| Planner returns no strategies | JSON parsing failure — CC output may be truncated; retry with fallback prompt |
| Builder returns no answer | SymPy tool error — check builder output log for error messages |
| All strategies fail | Try `--max-loops 5` for more replanning rounds |
| API rate limited | Reduce `--K` or add delay between calls |
| `pandas` not found | Use `.venv/bin/python` not bare `python` |

---

## License

MIT
