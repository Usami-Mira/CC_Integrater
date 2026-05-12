#!/usr/bin/env python3
"""
Claude Code Sandbox Manager — Orchestrator Edition (async).

Manages the full pipeline: Planner → Builder×K + Evaluator×K loops → Verifier → Summary.

This script runs OUTSIDE Claude Code's context. It:
1. Loads problems and answers from parquet
2. Launches Claude Code agents (Planner, Builder, Evaluator) with limited context
3. Answers (gold) NEVER enter the Claude context — only used here for verification
4. Handles all logging

Usage:
  python scripts/cc_orchestrator.py --parquet question_filtered_example.parquet --n 3 --K 3
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

# ── Config loader ────────────────────────────────────────────────────────────
# Reads from configs/{config,prompts,model}.yaml. CLI args override config.yaml values.

_CONFIGS_DIR = Path(__file__).parent.parent / "configs"


def _load_yaml(filename: str) -> dict:
    import yaml
    return yaml.safe_load((_CONFIGS_DIR / filename).read_text(encoding="utf-8"))


def load_all_configs() -> dict:
    config = _load_yaml("config.yaml")
    prompts = _load_yaml("prompts.yaml")
    model = _load_yaml("model.yaml")
    return {"config": config, "prompts": prompts, "model": model}


def _prompt(prompts: dict, key: str) -> str:
    """Get a CC orchestrator prompt from prompts['cc_orchestrator'][key]."""
    return prompts["cc_orchestrator"][key]


get_prompt = _prompt  # public alias


def _config_value(config: dict, *keys: str, default=None):
    """Walk nested config keys, e.g. _config_value(cfg, 'run', 'K', default=3)."""
    d = config
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
    return d


# ── Problem loader ───────────────────────────────────────────────────────────

def load_problems(parquet_path: str, max_rows: int | None = None) -> list[dict]:
    import pandas as pd
    df = pd.read_parquet(parquet_path)
    if max_rows:
        df = df.head(max_rows)

    problems = []
    for i, row in df.iterrows():
        question = str(row.get("question", "")).strip()
        answer = str(row.get("answer", "")).strip()
        pid = str(row.get("id", f"row_{i}"))
        tag = row.get("tag", {})
        if isinstance(tag, dict):
            problem_type = tag.get("problem_type", "expression")
        else:
            problem_type = "expression"

        if not question or len(question) < 2:
            continue

        problems.append({
            "problem_id": pid,
            "question": question,
            "gold_answer": answer,
            "problem_type": problem_type,
        })
    return problems


# ── Logging ──────────────────────────────────────────────────────────────────

class CCLogger:
    def __init__(self, log_dir: str):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        (self.log_dir / "traces").mkdir(exist_ok=True)

        self._lock = threading.Lock()
        self._output_f = open(self.log_dir / "output.log", "w", encoding="utf-8")

    def log(self, msg: str) -> None:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        print(line)
        with self._lock:
            self._output_f.write(line + "\n")
            self._output_f.flush()

    async def log_output(self, role: str, output: str) -> None:
        path = self.log_dir / f"{role}_output.log"
        await asyncio.to_thread(self._write_append, path, output + "\n")
        with self._lock:
            self._output_f.write(f"--- {role} output ({len(output)} chars) ---\n")
            self._output_f.flush()

    async def write_trace(self, problem_id: str, data: dict) -> None:
        trace_path = self.log_dir / "traces" / f"{problem_id}.json"
        md_path = self.log_dir / "traces" / f"{problem_id}.md"
        json_text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        md_text = _render_trace_md(data)
        await asyncio.gather(
            asyncio.to_thread(self._write_text, trace_path, json_text),
            asyncio.to_thread(self._write_text, md_path, md_text),
        )

    async def write_summary(self, summary: dict) -> None:
        summary_path = self.log_dir / "summary.json"
        md_path = self.log_dir / "summary.md"
        json_text = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
        md_text = _render_summary_md(summary)
        await asyncio.gather(
            asyncio.to_thread(self._write_text, summary_path, json_text),
            asyncio.to_thread(self._write_text, md_path, md_text),
        )

    @staticmethod
    def _write_text(path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def _write_append(path: Path, content: str) -> None:
        with open(path, "a", encoding="utf-8") as f:
            f.write(content)

    def close(self) -> None:
        self._output_f.close()


def _render_trace_md(data: dict) -> str:
    """Render a trace as a standard math solution with narrative steps."""
    lines = []
    lines.append(f"# {data.get('problem_id', '?')}")
    lines.append("")
    lines.append(f"**题目** {data.get('question', '?')}")
    lines.append("")
    lines.append(f"**标准答案** {data.get('gold_answer', '?')}")
    lines.append("")
    lines.append(f"**状态** {'✅ 正确' if data.get('status') == 'CORRECT' else '❌ 错误'}")
    lines.append("")

    if data.get("solutions"):
        lines.append("## 解题过程")
        lines.append("")

        for sol in data["solutions"]:
            if not sol:
                continue
            strat_id = sol.get("strategy_id", "?")
            strat_name = ""
            for s in data.get("strategies", []):
                if s and s.get("strategy_id") == strat_id:
                    strat_name = s.get("name", "")
                    break

            vr = sol.get("verifier_result") or {}
            is_correct = vr.get("is_eq", False)
            status_tag = "✅ 通过" if is_correct else "❌ 未通过"
            attempt = sol.get("attempt", 1)

            lines.append(f"### 方法 {strat_name}（第 {attempt} 次尝试）— {status_tag}")
            lines.append("")

            if sol.get("steps"):
                for step in sol["steps"]:
                    if not step:
                        continue
                    thought = step.get("thought", "")
                    result = step.get("result", "")
                    tool = step.get("tool") or ""
                    args = step.get("args") or {}

                    expr = args.get("expr_str", "")
                    var = args.get("var", "")
                    mapping = args.get("mapping", "")
                    step_no = step.get("step", "")

                    _render_step(lines, step_no, tool, thought, result, expr, var, mapping)

            lines.append(f"**结果**  $$ {sol.get('final_answer', '')} $$")
            lines.append("")

            vr = sol.get("verifier_result") or {}
            if vr:
                lines.append(f"验证：{vr.get('evidence', '')}（{vr.get('level_used', '?')}）")
                lines.append("")

            lines.append("---")
            lines.append("")

        lines.append(f"## 最终结果")
        lines.append("")
        if data.get("answer"):
            lines.append(f"$$ {data['answer']} $$")
            lines.append("")
            lines.append(f"最佳方法：{data.get('best_strategy', 'N/A')}")
            lines.append("")

    lines.append(f"验证等级：{data.get('verifier_level', 'N/A')} | 总循环数：{data.get('loops', 0)}")

    return "\n".join(lines)


def _render_step(lines, step_no, tool, thought, result, expr, var, mapping):
    """Append a single step as natural math prose."""
    if tool == "simplify":
        lines.append(f"Step {step_no}：化简 ${expr}$")
        lines.append(f"得 ${result}$")
    elif tool == "integrate_indef":
        lines.append(f"Step {step_no}：对 ${expr}$ 关于 {var} 积分")
        lines.append(f"得 ${result}$")
    elif tool == "integrate_def":
        lines.append(f"Step {step_no}：对 ${expr} 关于 {var} 在区间 [{mapping}] 上积分")
        lines.append(f"得 ${result}$")
    elif tool == "differentiate":
        lines.append(f"Step {step_no}：求导验证")
        lines.append(f"得 ${result}$")
    elif tool == "substitute":
        lines.append(f"Step {step_no}：代入 {mapping}")
        lines.append(f"得 ${result}$")
    elif tool == "limit":
        lines.append(f"Step {step_no}：求 {expr} 当 {var} → {mapping} 的极限")
        lines.append(f"得 ${result}$")
    elif tool == "series":
        lines.append(f"Step {step_no}：对 {expr} 在 {var} = {mapping} 处展开")
        lines.append(f"得 ${result}$")
    elif tool == "parse":
        lines.append(f"Step {step_no}：解析表达式 {expr}")
        if result:
            lines.append(f"得 ${result}$")
    elif tool == "solve":
        lines.append(f"Step {step_no}：解方程 {expr}")
        if result:
            lines.append(f"得 ${result}$")
    else:
        lines.append(f"Step {step_no}：{thought}")
        if result:
            lines.append(f"得 ${result}$")
    lines.append("")


def _render_summary_md(summary: dict) -> str:
    """Render summary as human-readable Markdown."""
    lines = []
    lines.append("# Solving Summary\n")
    lines.append(f"- **Total:** {summary['total']}\n")
    lines.append(f"- **Correct:** {summary['correct']}\n")
    lines.append(f"- **Wrong:** {summary['wrong']}\n")
    lines.append(f"- **Accuracy:** {summary['accuracy']:.1%}\n")
    lines.append(f"- **Verifier Levels:** {json.dumps(summary.get('verifier_levels', {}))}\n\n")

    lines.append("## Per-Problem Results\n\n")
    lines.append("| # | Problem | Status | Answer | Strategy | Level |\n")
    lines.append("|---|---------|--------|--------|----------|-------|\n")
    for i, p in enumerate(summary.get("per_problem", []), 1):
        status = "✅" if p["status"] == "CORRECT" else "❌"
        ans = (p.get("answer", "") or "")[:40]
        lines.append(f"| {i} | {p['problem_id']} | {status} {p['status']} | `{ans}` | {p.get('best_strategy', '')} | {p.get('verifier_level', 'N/A')} |\n")

    lines.append(f"\n## Most Successful Strategies\n\n")
    for strat, count in sorted(summary.get("strategies_success", {}).items(), key=lambda x: -x[1]):
        lines.append(f"- {strat}: {count} problem(s)\n")

    return "\n".join(lines)


# ── Claude Code Agent invoker (async) ────────────────────────────────────────

async def run_cc_agent(prompt: str, timeout: int = 300) -> str:
    """Run Claude Code in --print mode with all permissions skipped.

    Passes the prompt via stdin to avoid CLI argument length limits that
    can truncate large prompts.
    """
    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", "--dangerously-skip-permissions",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE,
        env={**{k: v for k, v in os.environ.items() if v is not None}, "CLAUDE_CODE_NO_ANALYTICS": "1"},
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(prompt.encode()),
            timeout=timeout,
        )
        return stdout.decode().strip()
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return ""


# ── Verifier (pure Python, gold answer never enters Claude context) ───────────

async def run_verifier(pred: str, gold: str, var: str = "x",
                       answer_type: str = "expression", question: str = "",
                       n_samples: int = 30) -> dict:
    """Run L1-L4 verification in a thread so CPU-bound SymPy doesn't block the event loop. Gold answer stays here — Claude never sees it."""
    from calc_solver.tools.verifier import Verifier
    try:
        v = Verifier(llm_client=None, llm_for_unsure=False, n_samples=n_samples)
        # is_equivalent is async but its L2/L3/L4 checks are CPU-bound SymPy;
        # offload to a thread so other problems can proceed concurrently.
        r = await asyncio.to_thread(
            lambda: asyncio.run(v.is_equivalent(pred, gold, var=var, answer_type=answer_type, question=question))
        )
        return r.model_dump()
    except Exception as e:
        err = str(e)[:200]
        return {"is_eq": False, "level_used": "fail", "confidence": 0.0,
                "evidence": err}


async def run_l5_arbitration(pred: str, gold: str, question: str = "",
                             answer_type: str = "expression",
                             prompt_template: str = "", timeout: int = 120) -> dict:
    """L5: Claude judges equivalence between two expressions (blind)."""
    prompt = prompt_template.format(
        question=question[:200] if question else "N/A",
        pred=pred, gold=gold,
    )
    raw = await run_cc_agent(prompt, timeout=timeout)
    try:
        import re
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception:
        pass
    return {"equivalent": False, "reason": f"L5 parse error: {raw[:100]}"}


# ── Pipeline logic ───────────────────────────────────────────────────────────

async def solve_one_problem(problem: dict, K: int, max_steps: int, max_loops: int,
                            logger: CCLogger, prompts: dict,
                            cc_timeouts: dict, verifier_cfg: dict) -> dict:
    """Full pipeline for one problem. Returns trace data."""
    logger.log(f"=== Problem: {problem['problem_id']} ===")
    logger.log(f"  Question: {problem['question'][:80]}...")

    trace = {
        "problem_id": problem["problem_id"],
        "question": problem["question"],
        "gold_answer": problem["gold_answer"],
        "status": "WRONG",
        "answer": "",
        "best_strategy": "",
        "verifier_level": "N/A",
        "verifier_result": None,
        "loops": 0,
        "strategies": [],
        "solutions": [],
    }

    n_samples = verifier_cfg.get("n_samples", 30)

    for loop_idx in range(max_loops):
        trace["loops"] = loop_idx + 1

        # Phase 1: Planner (with JSON parse retry)
        logger.log(f"  Loop {loop_idx+1}: Planning...")
        if loop_idx == 0:
            planner_prompt = _prompt(prompts, "planner").format(
                question=problem["question"],
                problem_type=problem["problem_type"],
                K=K,
            )
            planner_timeout = cc_timeouts.get("cc_timeout_planner", 180)
        else:
            failed_names = ", ".join(s["name"] for s in trace["strategies"][-K:])
            planner_prompt = _prompt(prompts, "replan").format(
                question=problem["question"],
                failed=failed_names,
                K=K,
            )
            planner_timeout = cc_timeouts.get("cc_timeout_planner_fallback", 120)

        planner_output = await run_cc_agent(planner_prompt, timeout=planner_timeout)
        await logger.log_output("planner", planner_output)

        strategies = parse_strategies(planner_output, K)
        if not strategies:
            logger.log("  Planner JSON parse failed, retrying with stricter prompt...")
            fallback = _prompt(prompts, "planner_fallback").format(
                question=problem["question"], K=K)
            planner_output = await run_cc_agent(
                fallback, timeout=cc_timeouts.get("cc_timeout_planner_fallback", 120))
            await logger.log_output("planner_retry", planner_output)
            strategies = parse_strategies(planner_output, K)
            if not strategies:
                logger.log("  Planner still returned no strategies, giving up")
                break
        trace["strategies"].extend(strategies)
        logger.log(f"  Got {len(strategies)} strategies: {[s['name'] for s in strategies]}")

        # Phase 2: Builder × K + Evaluator loop
        for strat in strategies:
            logger.log(f"  Building strategy: {strat['name']}...")

            # Builder ↔ Evaluator loop (max 2 retries)
            best_solution = None
            retry_feedback = None

            for retry_idx in range(2):
                if retry_idx == 0:
                    builder_prompt = _prompt(prompts, "builder").format(
                        question=problem["question"],
                        strategy_name=strat["name"],
                        strategy_rationale=strat["rationale"],
                        steps_outline="\n".join(f"  {i+1}. {s}" for i, s in enumerate(strat["steps_outline"])),
                    )
                else:
                    issues = retry_feedback.get("issues", []) if retry_feedback else []
                    feedback = retry_feedback.get("feedback", "") if retry_feedback else ""
                    prev = best_solution.get("final_answer", "") if best_solution else ""
                    builder_prompt = _prompt(prompts, "builder_retry").format(
                        question=problem["question"],
                        strategy_name=strat["name"],
                        strategy_rationale=strat["rationale"],
                        steps_outline="\n".join(f"  {i+1}. {s}" for i, s in enumerate(strat["steps_outline"])),
                        previous_answer=prev,
                        evaluator_issues=json.dumps(issues),
                        evaluator_feedback=feedback,
                    )

                builder_timeout = cc_timeouts.get("cc_timeout_builder", 300)
                builder_output = await run_cc_agent(builder_prompt, timeout=builder_timeout)
                await logger.log_output(f"builder_{retry_idx+1}", builder_output)

                solution = parse_builder_output(builder_output)
                pred = solution.get("final_answer_sympy") or solution.get("final_answer", "")
                if not pred:
                    logger.log(f"  Builder (attempt {retry_idx+1}) returned no answer")
                    break

                # Verifier (pure Python, gold stays in orchestrator)
                vr = await run_verifier(
                    pred, problem["gold_answer"],
                    var="x", answer_type="expression",
                    question=problem["question"],
                    n_samples=n_samples,
                )
                logger.log(f"  Verifier (attempt {retry_idx+1}): is_eq={vr['is_eq']}, level={vr['level_used']}")

                # Evaluator (receives only bool from Verifier, not gold_answer)
                evaluator_prompt = _prompt(prompts, "evaluator").format(
                    question=problem["question"],
                    strategy_name=strat["name"],
                    builder_answer=pred[:200],
                    steps_summary=solution.get("steps_summary", ""),
                    verifier_verdict=vr["is_eq"],
                )
                evaluator_timeout = cc_timeouts.get("cc_timeout_evaluator", 120)
                evaluator_output = await run_cc_agent(evaluator_prompt, timeout=evaluator_timeout)
                await logger.log_output("evaluator", evaluator_output)
                evaluator_result = parse_evaluator_output(evaluator_output)

                trace["solutions"].append({
                    "strategy_id": strat["strategy_id"],
                    "attempt": retry_idx + 1,
                    "final_answer": solution.get("final_answer", ""),
                    "final_answer_sympy": solution.get("final_answer_sympy", ""),
                    "steps_summary": solution.get("steps_summary", ""),
                    "steps": solution.get("steps", []),
                    "builder_raw_output": builder_output[:2000],
                    "verifier_result": vr,
                    "evaluator_passed": evaluator_result.get("passed", vr["is_eq"]),
                })

                if vr["is_eq"]:
                    logger.log(f"  ✓ CORRECT via {vr['level_used']}")
                    trace["status"] = "CORRECT"
                    trace["answer"] = solution.get("final_answer", pred)
                    trace["best_strategy"] = strat["name"]
                    trace["verifier_level"] = vr["level_used"]
                    trace["verifier_result"] = vr
                    trace["builder_raw_output"] = builder_output
                    best_solution = solution
                    break

                if not evaluator_result.get("should_retry", False):
                    logger.log(f"  Evaluator says give up: {evaluator_result.get('issues', [])}")
                    break

                retry_feedback = evaluator_result
                logger.log(f"  Evaluator says retry: {evaluator_result.get('feedback', '')[:100]}")

        if trace["status"] == "CORRECT":
            logger.log(f"  Loop {loop_idx+1}: finished, we have a correct answer")
            break

        logger.log(f"  Loop {loop_idx+1}: all strategies failed, replanning...")

    if trace["status"] != "CORRECT":
        logger.log("  ✗ WRONG — no strategy succeeded")

    return trace


def parse_strategies(raw: str, K: int) -> list[dict]:
    j = _extract_json(raw)
    if j:
        try:
            data = json.loads(j)
            strategies = data.get("strategies", [])
            return strategies[:K]  # enforce exactly K
        except Exception:
            return []
    return []


def _extract_json(raw: str) -> str | None:
    """Extract first parseable JSON object from text that may contain LaTeX braces."""
    import re

    # Strategy 1: Extract content between code fences and try each one
    fences = re.split(r"```(?:json)?", raw)
    for i, section in enumerate(fences):
        if i == 0:
            continue  # Content before first fence
        # Split on closing fence
        parts = section.split("```", 1)
        content = parts[0].strip()
        if content:
            try:
                json.loads(content)
                return content
            except Exception:
                # Try repairing truncated JSON (Claude sometimes cuts off mid-output)
                repaired = _repair_truncated_json(content)
                if repaired is not None:
                    return repaired

    # Strategy 2: Find JSON-like content by brace counting, but skip braces inside quoted strings
    depth = 0
    in_string = False
    escape = False
    start = None
    for i, ch in enumerate(raw):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                candidate = raw[start:i+1]
                try:
                    json.loads(candidate)
                    return candidate
                except Exception:
                    repaired = _repair_truncated_json(candidate)
                    if repaired is not None:
                        return repaired
                start = None

    # If the loop ended with unclosed braces (truncated JSON), try repair
    if depth > 0 and start is not None:
        candidate = raw[start:]
        repaired = _repair_truncated_json(candidate)
        if repaired is not None:
            return repaired

    return None


def _repair_truncated_json(content: str) -> str | None:
    """Attempt to fix a JSON string that was truncated mid-output.

    Claude --print sometimes cuts off the last few characters or adds an
    extra closing brace. This tries several repair strategies.
    """
    # Walk through the content tracking depth of [], {}, and ""
    closing = []
    in_string = False
    escape = False

    for i, ch in enumerate(content):
        if escape:
            escape = False
            continue
        if ch == "\\":
            if i + 1 < len(content) and content[i + 1] == '"':
                continue
            escape = True
            continue
        if ch == '"':
            if in_string:
                in_string = False
            else:
                in_string = True
            continue
        if not in_string:
            if ch in "[{":
                closing.append("]" if ch == "[" else "}")
            elif ch == "]":
                if closing and closing[-1] == "]":
                    closing.pop()
            elif ch == "}":
                if closing and closing[-1] == "}":
                    closing.pop()

    # Strategy A: close unclosed brackets/braces
    if in_string or closing:
        fix = []
        if in_string:
            fix.append('"')
        fix.extend(reversed(closing))
        candidate = content + "".join(fix)
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            pass

    # Strategy B: strip trailing } chars and add ]} (handles extra } at end)
    stripped = content.rstrip("}").rstrip()
    if stripped and len(stripped) < len(content):
        for suffix in ("]}", "]}"):
            candidate = stripped + suffix
            try:
                json.loads(candidate)
                return candidate
            except Exception:
                pass

    # Strategy C: targeted truncation — only cut near the end where we
    # expect truncation, and require the result to be a "real" JSON object
    # (i.e. must contain a colon, ruling out bare "{}").
    for cut in range(len(content) - 1, max(0, len(content) - 300), -1):
        for suffix in ("]}", "]}", "]", "}"):
            candidate = content[:cut] + suffix
            if ":" not in candidate:
                continue  # skip bare braces like {} from LaTeX
            try:
                json.loads(candidate)
                return candidate
            except Exception:
                pass

    return None


def parse_builder_output(raw: str) -> dict:
    # Strip markdown code fence wrappers if present
    import re
    m = re.search(r"```\s*json\s*\n(.*?)\n```", raw, re.DOTALL)
    if m:
        raw = m.group(1)
    # Fix LaTeX backslashes BEFORE extraction so _extract_json can parse
    raw = _fix_latex_escapes(raw)
    j = _extract_json(raw)
    if j:
        try:
            data = json.loads(j)
            # Clean any lingering code fence markers from string fields
            for key in ("final_answer", "final_answer_sympy", "steps_summary"):
                if key in data and isinstance(data[key], str):
                    data[key] = re.sub(r"```", "", data[key]).strip()
            return data
        except Exception:
            return {}
    return {}


def _fix_latex_escapes(json_str: str) -> str:
    """Double all backslashes in JSON string values so LaTeX survives json.loads."""
    import re

    def _fix_value(m):
        inner = m.group(1)
        # Double every backslash — JSON parser will turn \\ back into single \
        result = inner.replace("\\", "\\\\")
        return '"' + result + '"'

    # Match JSON string values (handles escaped quotes inside)
    return re.sub(r'"((?:[^"\\]|\\.)*)"', _fix_value, json_str)


def parse_evaluator_output(raw: str) -> dict:
    j = _extract_json(raw)
    if j:
        try:
            data = json.loads(j)
            if "passed" not in data and "is_correct" in data:
                data["passed"] = data["is_correct"]
            elif "passed" not in data:
                data["passed"] = False
            if "should_retry" not in data:
                data["should_retry"] = not data["passed"]
            if "issues" not in data:
                data["issues"] = []
            if "feedback" not in data:
                data["feedback"] = ""
            if "retry_hint" not in data:
                data["retry_hint"] = ""
            return data
        except Exception:
            return {"passed": False, "should_retry": False, "issues": [], "feedback": "parse_error", "retry_hint": ""}
    return {"passed": False, "should_retry": False, "issues": [], "feedback": "", "retry_hint": ""}


def build_summary(traces: list[dict]) -> dict:
    total = len(traces)
    correct = sum(1 for t in traces if t["status"] == "CORRECT")
    wrong = total - correct

    verifier_levels = {}
    strategies_success = {}
    for t in traces:
        if t["status"] == "CORRECT":
            lvl = t.get("verifier_level", "N/A")
            verifier_levels[lvl] = verifier_levels.get(lvl, 0) + 1
            strat = t.get("best_strategy", "")
            if strat:
                strategies_success[strat] = strategies_success.get(strat, 0) + 1

    return {
        "total": total,
        "correct": correct,
        "wrong": wrong,
        "accuracy": round(correct / total, 4) if total > 0 else 0.0,
        "verifier_levels": verifier_levels,
        "strategies_success": strategies_success,
        "per_problem": [
            {
                "problem_id": t["problem_id"],
                "status": t["status"],
                "answer": t.get("answer", ""),
                "best_strategy": t.get("best_strategy", ""),
                "verifier_level": t.get("verifier_level", "N/A"),
                "loops": t.get("loops", 0),
            }
            for t in traces
        ],
    }


# ── Entry point ──────────────────────────────────────────────────────────────

async def _solve_and_write(problem: dict, K: int, max_steps: int, max_loops: int,
                           logger: CCLogger, idx: int, semaphore: asyncio.Semaphore,
                           prompts: dict, cc_timeouts: dict, verifier_cfg: dict) -> dict:
    """Worker: solve one problem and write its trace. Returns trace dict."""
    async with semaphore:
        logger.log(f"[worker] === Problem: {problem['problem_id']} ===")
        trace = await solve_one_problem(
            problem, K, max_steps, max_loops, logger, prompts, cc_timeouts, verifier_cfg)
        await logger.write_trace(problem["problem_id"], trace)
        return trace


async def main_async(args, all_cfg: dict):
    config = all_cfg["config"]
    prompts = all_cfg["prompts"]

    # Resolve defaults from config.yaml (CLI args override)
    cfg_run = config.get("run", {})
    cfg_data = config.get("data", {})
    cfg_verifier = config.get("verifier", {})

    parquet_path = args.parquet or cfg_data.get("parquet_file", "question_filtered_example.parquet")
    K = args.K if args.K is not None else cfg_run.get("K", 3)
    max_steps = args.max_steps if args.max_steps is not None else cfg_run.get("builder_max_steps", 12)
    max_loops = args.max_loops if args.max_loops is not None else cfg_run.get("max_outer_loops", 3)
    workers = args.workers if args.workers is not None else cfg_run.get("problem_concurrency", 8)
    n_samples = cfg_verifier.get("n_samples", 30)

    # Build CC timeout dict from config
    cc_timeouts = {
        "cc_timeout_planner": cfg_run.get("cc_timeout_planner", 180),
        "cc_timeout_planner_fallback": cfg_run.get("cc_timeout_planner_fallback", 120),
        "cc_timeout_builder": cfg_run.get("cc_timeout_builder", 300),
        "cc_timeout_evaluator": cfg_run.get("cc_timeout_evaluator", 120),
        "cc_timeout_l5": cfg_run.get("cc_timeout_l5", 120),
    }

    verifier_cfg = {"n_samples": n_samples}

    # Load problems
    problems = load_problems(parquet_path, max_rows=args.n)
    if args.id:
        problems = [p for p in problems if p["problem_id"] == args.id]

    if not problems:
        print("No problems to solve.")
        sys.exit(1)

    print(f"Loaded {len(problems)} problems from {parquet_path}")

    # Create log directory (from config)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_base = config.get("paths", {}).get("log_dir", "logs/cc")
    log_dir = f"{log_base}/{timestamp}"
    logger = CCLogger(log_dir)

    print(f"Log directory: {log_dir}")
    print(f"Workers: {workers}")
    print("")

    try:
        semaphore = asyncio.Semaphore(workers)

        async def _indexed_solve(idx, problem):
            try:
                trace = await _solve_and_write(
                    problem, K, max_steps, max_loops, logger, idx, semaphore,
                    prompts, cc_timeouts, verifier_cfg)
                return idx, trace, None
            except Exception as e:
                return idx, None, e

        coros = [_indexed_solve(i, problem) for i, problem in enumerate(problems)]

        traces = [None] * len(problems)
        done_count = 0
        for coro in asyncio.as_completed(coros):
            idx, trace, exc = await coro
            if exc:
                logger.log(f"  Problem {problems[idx]['problem_id']} crashed: {exc}")
                traces[idx] = {
                    "problem_id": problems[idx]["problem_id"],
                    "question": problems[idx]["question"],
                    "gold_answer": problems[idx]["gold_answer"],
                    "status": "WRONG", "answer": "", "best_strategy": "",
                    "verifier_level": "N/A", "verifier_result": None,
                    "loops": 0, "strategies": [], "solutions": [],
                }
            else:
                traces[idx] = trace
            done_count += 1
            logger.log(f"[{done_count}/{len(problems)}] problems completed")

        traces = [t for t in traces if t is not None]

        # Build and save summary
        summary = build_summary(traces)
        await logger.write_summary(summary)

        # Print summary
        print(f"\n{'='*60}")
        print(f"SUMMARY")
        print(f"{'='*60}")
        print(f"  Total:     {summary['total']}")
        print(f"  Correct:   {summary['correct']}")
        print(f"  Wrong:     {summary['wrong']}")
        print(f"  Accuracy:  {summary['accuracy']:.1%}")
        print(f"  Levels:    {json.dumps(summary['verifier_levels'])}")
        print(f"{'='*60}")
        print(f"\n{'problem_id':<15} {'status':<10} {'answer':<30} {'strategy':<15} {'level'}")
        print("-" * 100)
        for p in summary["per_problem"]:
            ans = (p["answer"] or "")[:28]
            print(f"{p['problem_id']:<15} {p['status']:<10} {ans:<30} {p.get('best_strategy',''):<15} {p.get('verifier_level','')}")

    finally:
        logger.close()


def main():
    parser = argparse.ArgumentParser(description="Claude Code Orchestrator — Sandboxed Pipeline")
    parser.add_argument("--parquet", default=None, help="Parquet file (default from config.yaml)")
    parser.add_argument("--n", type=int, default=None, help="Max problems")
    parser.add_argument("--id", type=str, default=None, help="Specific problem ID")
    parser.add_argument("--K", type=int, default=None, help="Strategies per problem (default from config.yaml)")
    parser.add_argument("--max-steps", type=int, default=None, help="Max steps per builder (default from config.yaml)")
    parser.add_argument("--max-loops", type=int, default=None, help="Max replanning loops (default from config.yaml)")
    parser.add_argument("--workers", type=int, default=None, help="Parallel problem concurrency (default from config.yaml)")
    args = parser.parse_args()
    all_cfg = load_all_configs()
    asyncio.run(main_async(args, all_cfg))


if __name__ == "__main__":
    main()
