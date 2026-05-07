"""Run a full pipeline session with a mock LLM to verify end-to-end flow."""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent / "src"))

from calc_solver.agents.builder import BuilderAgent
from calc_solver.agents.evaluator import EvaluatorAgent
from calc_solver.agents.planner import PlannerAgent
from calc_solver.data.loader import load_parquet
from calc_solver.llm.client import QwenClient
from calc_solver.orchestrator.pipeline import Pipeline
from calc_solver.tools.verifier import Verifier
from calc_solver.utils.logger import RunLogger
from calc_solver.utils.ids import make_run_id

# --- Known problems ---

PROBLEMS = {
    "synth_01": {
        "tool_seq": [("integrate_indef", {"expr_str": "x", "var": "x"})],
        "answer": "x**2/2",
    },
    "synth_02": {
        "tool_seq": [("integrate_indef", {"expr_str": "3*x**2", "var": "x"})],
        "answer": "x**3",
    },
    "synth_03": {
        "tool_seq": [("integrate_def", {"expr_str": "2*x", "var": "x", "a_str": "0", "b_str": "1"})],
        "answer": "1",
    },
    "synth_04": {
        "tool_seq": [("integrate_indef", {"expr_str": "cos(x)", "var": "x"})],
        "answer": "sin(x)",
    },
    "synth_05": {
        "tool_seq": [("differentiate", {"expr_str": "x**3 + 2*x", "var": "x"})],
        "answer": "3*x**2 + 2",
    },
}

STRATEGIES_MAP = {
    "indefinite_integral": [
        {"strategy_id": "s1", "name": "power_rule", "rationale": "Direct power rule",
         "steps_outline": ["Identify integrand", "Apply power rule", "Add C"]},
        {"strategy_id": "s2", "name": "substitution", "rationale": "Change of variable",
         "steps_outline": ["Choose u", "Substitute", "Integrate"]},
        {"strategy_id": "s3", "name": "by_parts", "rationale": "Integration by parts",
         "steps_outline": ["Set u, dv", "Apply formula"]},
    ],
    "definite_integral": [
        {"strategy_id": "s1", "name": "fundamental_theorem", "rationale": "Antiderivative at bounds",
         "steps_outline": ["Find antiderivative", "Evaluate bounds", "Subtract"]},
        {"strategy_id": "s2", "name": "geometric", "rationale": "Area interpretation",
         "steps_outline": ["Identify shape", "Compute area"]},
        {"strategy_id": "s3", "name": "numeric", "rationale": "Riemann sum",
         "steps_outline": ["Partition interval", "Sum rectangles"]},
    ],
    "derivative": [
        {"strategy_id": "s1", "name": "power_rule", "rationale": "Term-by-term differentiation",
         "steps_outline": ["Differentiate each term", "Simplify"]},
        {"strategy_id": "s2", "name": "definition", "rationale": "Limit definition",
         "steps_outline": ["Difference quotient", "Take limit"]},
        {"strategy_id": "s3", "name": "log_diff", "rationale": "Logarithmic differentiation",
         "steps_outline": ["Take log", "Differentiate implicitly"]},
    ],
}


def _classify_question(q: str) -> str:
    """Find problem_id from question content."""
    if r"\int_{0}^{1}" in q or r"\int_0^1" in q:
        return "synth_03"
    if "cos" in q:
        return "synth_04"
    if r"\frac{d}" in q or "d/dx" in q:
        return "synth_05"
    if "3" in q and "x" in q:
        return "synth_02"
    if "x" in q and r"\int" in q:
        return "synth_01"
    return "synth_01"


def _detect_problem_type(q: str) -> str:
    if r"\int_{0}" in q or r"\int_0" in q:
        return "definite_integral"
    if r"\frac{d}" in q or "d/dx" in q:
        return "derivative"
    if r"\int" in q:
        return "indefinite_integral"
    return "indefinite_integral"


class MockLLM:
    """Content-aware mock that inspects messages to determine response."""

    async def chat(self, messages: list[dict], **kwargs) -> str:
        agent_name = kwargs.get("agent_name", "unknown")

        # Find the initial user message (has the question)
        initial_user = ""
        for m in messages:
            if m.get("role") == "user":
                c = m.get("content", "")
                if r"\int" in c or r"\frac" in c or "d/dx" in c:
                    initial_user = c
                    break

        problem_id = _classify_question(initial_user)
        problem_data = PROBLEMS[problem_id]
        ptype = _detect_problem_type(initial_user)

        if agent_name == "planner":
            strategies = STRATEGIES_MAP.get(ptype, STRATEGIES_MAP["indefinite_integral"])
            return json.dumps({"strategies": strategies})

        if agent_name == "builder":
            # Count tool calls already made in this conversation
            assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
            tool_calls_made = []
            for msg in assistant_msgs:
                try:
                    data = json.loads(msg.get("content", ""))
                    if isinstance(data, dict) and data.get("action") == "tool":
                        tool_calls_made.append(data.get("tool"))
                except Exception:
                    pass

            if not tool_calls_made:
                # First step: use the primary tool
                tool_name, tool_args = problem_data["tool_seq"][0]
                return json.dumps({
                    "action": "tool", "thought": f"Use {tool_name}",
                    "current_state": "computing",
                    "tool": tool_name, "args": tool_args,
                })

            if len(tool_calls_made) == 1:
                # Second step: simplify
                return json.dumps({
                    "action": "tool", "thought": "Simplify result",
                    "current_state": "simplifying",
                    "tool": "simplify", "args": {"expr_str": "x"},
                })

            # Third step: finish
            return json.dumps({
                "action": "finish", "thought": "Solution found",
                "current_state": "done",
                "final_answer": problem_data["answer"],
                "final_answer_sympy": problem_data["answer"],
            })

        if agent_name == "evaluator":
            return json.dumps({"best_id": "s1", "reason": "looks correct"})

        return "{}"


async def main():
    print("=" * 60)
    print("Running full pipeline session with mock LLM")
    print("=" * 60)

    # Load problems
    problems = load_parquet("data/raw/synth-v1.parquet")
    print(f"\nLoaded {len(problems)} problems:")
    for p in problems:
        tag = p.metadata.get("tag", {})
        print(f"  {p.problem_id}: {p.question[:50]} | type={p.answer_type} | indefinite={tag.get('have_indefinite', False)}")

    # Create logger
    run_id = make_run_id()
    print(f"\nRun ID: {run_id}")
    logger = RunLogger(run_id)

    # Create mock client
    mock_llm = MockLLM()
    client = MagicMock()
    client.chat = mock_llm.chat

    # Build pipeline
    planner = PlannerAgent(client=client, logger=logger)
    builder = BuilderAgent(client=client, max_steps=10, max_retries=1, logger=logger)
    verifier = Verifier(llm_client=None, llm_for_unsure=False, logger=logger)
    evaluator = EvaluatorAgent(client=client, verifier=verifier, logger=logger)

    pipeline = Pipeline(
        planner=planner, builder=builder, evaluator=evaluator,
        K=3, max_outer_loops=2,
        problem_concurrency=2, builder_concurrency_per_problem=3,
        logger=logger,
    )

    print(f"\n{'=' * 60}")
    print("Starting pipeline...")
    print(f"{'=' * 60}")

    try:
        results = await pipeline.run_batch(problems)
    finally:
        logger.close()

    # Report
    print(f"\n{'=' * 60}")
    print("RESULTS")
    print(f"{'=' * 60}")

    correct = 0
    for r in results:
        status = "CORRECT" if r.is_correct else "WRONG"
        if r.is_correct:
            correct += 1
        print(f"\n  {r.problem_id}: {status}")
        print(f"    Strategy:   {r.chosen_strategy_id}")
        print(f"    Answer:     {r.final_answer}")
        print(f"    Confidence: {r.confidence:.2f}")
        print(f"    Loop:       {r.loop_count}")
        print(f"    Agreement:  {r.method_agreement}")
        if r.notes:
            print(f"    Notes:      {r.notes}")

    total = len([r for r in results if r.notes != "skipped_resume"])
    print(f"\n{'=' * 60}")
    print(f"Accuracy: {correct}/{total} = {correct/total:.1%}")
    print(f"Logs:     logs/{run_id}/")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
