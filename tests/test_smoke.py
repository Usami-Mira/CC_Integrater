#!/usr/bin/env python3
"""
Smoke test for the async orchestrator.

Exercises all async plumbing and parsing logic without calling Claude Code.
"""
import asyncio
import json
import sys
from pathlib import Path

# Ensure we import from the scripts dir
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cc_orchestrator import (
    _extract_json,
    _fix_latex_escapes,
    _config_value,
    build_summary,
    get_prompt,
    load_all_configs,
    parse_builder_output,
    parse_evaluator_output,
    parse_strategies,
    run_verifier,
)

passed = 0
failed = 0


def ok(name):
    global passed
    passed += 1
    print(f"  PASS  {name}")


def fail(name, exc):
    global failed
    failed += 1
    print(f"  FAIL  {name}: {exc}")


# ── 1. Parsing ──────────────────────────────────────────────────────────────

print("── Parsing ──")

# 1a. Parse strategies from valid JSON
try:
    raw = '{"strategies": [{"strategy_id": "s1", "name": "u-sub", "rationale": "fast", "steps_outline": ["sub u=x+1", "integrate"]}]}'
    result = parse_strategies(raw, 1)
    assert len(result) == 1
    assert result[0]["strategy_id"] == "s1"
    ok("parse_strategies valid JSON")
except Exception as e:
    fail("parse_strategies valid JSON", e)

# 1b. Parse strategies from JSON inside code fence
try:
    raw = "Sure! Here you go:\n```json\n{\"strategies\": [{\"strategy_id\": \"s1\", \"name\": \"parts\", \"rationale\": \"r\", \"steps_outline\": [\"u=x\", \"dv=dx\"]}]}\n```\nDone."
    result = parse_strategies(raw, 1)
    assert len(result) == 1
    assert result[0]["name"] == "parts"
    ok("parse_strategies code fence")
except Exception as e:
    fail("parse_strategies code fence", e)

# 1c. Parse strategies from invalid JSON → empty
try:
    result = parse_strategies("hello world", 1)
    assert result == []
    ok("parse_strategies invalid")
except Exception as e:
    fail("parse_strategies invalid", e)

# 1d. Parse strategies enforce K limit
try:
    raw = '{"strategies": [{"strategy_id": "s1", "name": "a", "rationale": "r", "steps_outline": []}, {"strategy_id": "s2", "name": "b", "rationale": "r", "steps_outline": []}]}'
    result = parse_strategies(raw, 1)
    assert len(result) == 1
    ok("parse_strategies K limit")
except Exception as e:
    fail("parse_strategies K limit", e)

# 1e. Parse builder output with code fence
try:
    import re as _re
    # Simulate what cc_orchestrator does: strip fence, fix escapes, extract JSON
    raw_inner = '{"final_answer": "\\\\frac{x^2}{2}", "final_answer_sympy": "x**2/2", "steps": [{"step": 1, "tool": "integrate_indef", "args": {"expr_str": "x", "var": "x"}, "result": "x**2/2", "thought": "integrate"}], "steps_summary": "integrated x"}'
    raw = '```json\n' + raw_inner + '\n```'
    result = parse_builder_output(raw)
    assert "final_answer_sympy" in result
    assert result["final_answer_sympy"] == "x**2/2"
    assert len(result["steps"]) == 1
    ok("parse_builder_output code fence")
except Exception as e:
    fail("parse_builder_output code fence", e)

# 1f. Parse builder output without code fence (brace counting)
try:
    raw = '{"final_answer": "sin(x)", "final_answer_sympy": "sin(x)", "steps": [], "steps_summary": "done"}'
    result = parse_builder_output(raw)
    assert result["final_answer"] == "sin(x)"
    ok("parse_builder_output bare JSON")
except Exception as e:
    fail("parse_builder_output bare JSON", e)

# 1g. Parse evaluator output
try:
    raw = '{"passed": true, "issues": [], "feedback": "looks good", "should_retry": false}'
    result = parse_evaluator_output(raw)
    assert result["passed"] is True
    assert result["should_retry"] is False
    ok("parse_evaluator_output valid")
except Exception as e:
    fail("parse_evaluator_output valid", e)

# 1h. Parse evaluator output missing fields → defaults
try:
    raw = '{"equivalent": true}'
    result = parse_evaluator_output(raw)
    assert result["passed"] is False  # no "passed" field
    assert result["should_retry"] is True  # auto: not passed → retry
    ok("parse_evaluator_output defaults")
except Exception as e:
    fail("parse_evaluator_output defaults", e)

# 1i. _extract_json with LaTeX braces
try:
    raw = 'Answer: \\frac{1}{2} and the JSON is {"strategies": []}'
    result = _extract_json(raw)
    # Should find {"strategies": []} first (valid JSON), not try to parse LaTeX braces
    assert result == '{"strategies": []}'
    ok("_extract_json LaTeX braces")
except Exception as e:
    fail("_extract_json LaTeX braces", e)


# ── 2. async run_verifier ──────────────────────────────────────────────────

print("── Verifier ──")

# 2a. Identical strings → L1
try:
    r = asyncio.run(run_verifier("x**2/2", "x**2/2"))
    assert r["is_eq"] is True
    assert r["level_used"] == "L1"
    ok("verifier L1 string equal")
except Exception as e:
    fail("verifier L1 string equal", e)

# 2b. Different answers → fail
try:
    r = asyncio.run(run_verifier("x**2", "x**3"))
    assert r["is_eq"] is False
    ok("verifier different answers")
except Exception as e:
    fail("verifier different answers", e)

# 2c. Symbolic equivalence → L2
try:
    r = asyncio.run(run_verifier("sin(x)**2+cos(x)**2", "1"))
    assert r["is_eq"] is True
    assert r["level_used"] == "L2"
    ok("verifier L2 symbolic")
except Exception as e:
    fail("verifier L2 symbolic", e)

# 2d. Returns proper dict keys
try:
    r = asyncio.run(run_verifier("a", "b"))
    assert "is_eq" in r
    assert "level_used" in r
    assert "confidence" in r
    assert "evidence" in r
    ok("verifier return keys")
except Exception as e:
    fail("verifier return keys", e)


# ── 3. build_summary ────────────────────────────────────────────────────────

print("── Summary ──")

try:
    traces = [
        {"problem_id": "19_15", "status": "CORRECT", "answer": "x**2/2", "best_strategy": "u-sub", "verifier_level": "L2", "loops": 1},
        {"problem_id": "19_26", "status": "WRONG", "answer": "", "best_strategy": "", "verifier_level": "N/A", "loops": 3},
    ]
    summary = build_summary(traces)
    assert summary["total"] == 2
    assert summary["correct"] == 1
    assert summary["wrong"] == 1
    assert summary["accuracy"] == 0.5
    assert summary["strategies_success"] == {"u-sub": 1}
    assert summary["verifier_levels"] == {"L2": 1}
    ok("build_summary correct structure")
except Exception as e:
    fail("build_summary correct structure", e)


# ── 4. Concurrency ──────────────────────────────────────────────────────────

print("── Concurrency ──")

# 4a. asyncio.run works with async functions (smoke — no CC calls)
try:
    async def _test_async_flow():
        semaphore = asyncio.Semaphore(3)
        async with semaphore:
            r = await run_verifier("1", "1")
            return r

    r = asyncio.run(_test_async_flow())
    assert r["is_eq"] is True
    ok("async flow with semaphore")
except Exception as e:
    fail("async flow with semaphore", e)

# 4b. Multiple verifiers in parallel
try:
    async def _test_parallel():
        tasks = [
            asyncio.create_task(run_verifier("sin(x)**2+cos(x)**2", "1"))
            for _ in range(5)
        ]
        results = await asyncio.gather(*tasks)
        return all(r["is_eq"] for r in results)

    assert asyncio.run(_test_parallel())
    ok("5 parallel verifiers")
except Exception as e:
    fail("5 parallel verifiers", e)

# 4c. as_completed with indexed wrapper (exactly how orchestrator uses it)
try:
    async def _test_indexed_as_completed():
        semaphore = asyncio.Semaphore(3)

        async def _indexed_solve(idx):
            async with semaphore:
                await asyncio.sleep(0.01 * (idx % 3))  # stagger
                return idx, f"result_{idx}", None

        coros = [_indexed_solve(i) for i in range(5)]
        results = [None] * 5
        for coro in asyncio.as_completed(coros):
            idx, res, exc = await coro
            results[idx] = res
        return results

    result = asyncio.run(_test_indexed_as_completed())
    assert result == ["result_0", "result_1", "result_2", "result_3", "result_4"]
    ok("indexed as_completed pattern")
except Exception as e:
    fail("indexed as_completed pattern", e)


# ── 5. Config loading ────────────────────────────────────────────────────────

print("── Config loading ──")

# 5a. load_all_configs returns three sections
try:
    all_cfg = load_all_configs()
    assert "config" in all_cfg
    assert "prompts" in all_cfg
    assert "model" in all_cfg
    ok("load_all_configs returns 3 sections")
except Exception as e:
    fail("load_all_configs returns 3 sections", e)

# 5b. prompts has cc_orchestrator section with all keys
try:
    prompts = all_cfg["prompts"]
    cc = prompts["cc_orchestrator"]
    for key in ("planner", "planner_fallback", "replan", "builder", "builder_retry", "evaluator", "l5_judge"):
        assert key in cc, f"missing prompt key: {key}"
        assert len(cc[key]) > 10, f"prompt too short: {key}"
    ok("all CC orchestrator prompts present")
except Exception as e:
    fail("all CC orchestrator prompts present", e)

# 5c. config.yaml has expected sections
try:
    config = all_cfg["config"]
    assert "run" in config
    assert "data" in config
    assert "verifier" in config
    assert "paths" in config
    assert config["run"]["K"] == 3
    assert config["run"]["problem_concurrency"] == 8
    ok("config.yaml sections and values")
except Exception as e:
    fail("config.yaml sections and values", e)

# 5d. model.yaml is present and has model_id
try:
    model = all_cfg["model"]
    assert "model_id" in model
    assert "provider" in model
    ok("model.yaml present with model_id")
except Exception as e:
    fail("model.yaml present with model_id", e)

# 5e. get_prompt returns a string with placeholders
try:
    p = get_prompt(all_cfg["prompts"], "planner")
    assert "{K}" in p
    assert "{question}" in p
    ok("get_prompt returns template with placeholders")
except Exception as e:
    fail("get_prompt returns template with placeholders", e)

# 5f. _config_value walks nested keys
try:
    assert _config_value(all_cfg["config"], "run", "K") == 3
    assert _config_value(all_cfg["config"], "run", "max_outer_loops") == 3
    assert _config_value(all_cfg["config"], "data", "parquet_file") is not None
    assert _config_value(all_cfg["config"], "missing", "key", default="fallback") == "fallback"
    ok("_config_value walks nested keys")
except Exception as e:
    fail("_config_value walks nested keys", e)

# 5g. Prompts can be formatted without error
try:
    p = get_prompt(all_cfg["prompts"], "builder")
    formatted = p.format(
        question="integrate x dx",
        strategy_name="basic",
        strategy_rationale="trivial",
        steps_outline="1. integrate",
    )
    assert "integrate x dx" in formatted
    ok("builder prompt formats successfully")
except Exception as e:
    fail("builder prompt formats successfully", e)


# ── Result ──────────────────────────────────────────────────────────────────

print(f"\n{'='*40}")
print(f"  {passed} passed, {failed} failed")
print(f"{'='*40}")
sys.exit(1 if failed else 0)
