"""Enforce that solving agents cannot see the gold answer.

Two complementary approaches:

1. **Type isolation**: SolvingProblem has no gold_answer field. Any function
   that accepts SolvingProblem is structurally unable to access the answer.
   Tests verify the type contract (field absence, immutability, factory).

2. **Prompt scan**: Planner/Builder prompt templates are scanned against a
   known gold answer to catch accidental inclusion at prompt level.
"""
import pytest

from calc_solver.schema import Problem, SolvingProblem
from calc_solver.llm.prompts import get, format_prompt


# --- Type isolation tests ---

def _full_problem() -> Problem:
    return Problem(
        problem_id="t1",
        question=r"Compute $\int x \, dx$",
        gold_answer=r"\frac{x^{2}}{2} + C",
        answer_type="expression",
        variable="x",
        metadata={"tag": {"have_indefinite": True}},
    )


def test_solving_problem_has_no_gold_answer():
    """SolvingProblem must not have a gold_answer field."""
    sp = SolvingProblem(
        problem_id="x",
        question="Q",
        answer_type="expression",
        variable="x",
    )
    assert not hasattr(sp, "gold_answer")
    # Verify via model_fields (Pydantic v2, class-level access)
    assert "gold_answer" not in SolvingProblem.model_fields


def test_from_problem_strips_gold_answer():
    """SolvingProblem.from_problem must not carry gold_answer."""
    p = _full_problem()
    sp = SolvingProblem.from_problem(p)
    assert p.gold_answer  # original has it
    assert "gold_answer" not in SolvingProblem.model_fields
    assert sp.problem_id == p.problem_id
    assert sp.question == p.question
    assert sp.answer_type == p.answer_type
    assert sp.variable == p.variable


def test_solving_problem_is_a_pydantic_model():
    """SolvingProblem should be a proper Pydantic model for validation."""
    p = _full_problem()
    sp = SolvingProblem.from_problem(p)
    assert hasattr(sp, "model_dump")
    assert hasattr(sp, "model_validate")
    dump = sp.model_dump()
    assert "gold_answer" not in dump


def test_pipeline_passes_solving_problem_to_planner():
    """Verify type signature: PlannerAgent.plan accepts SolvingProblem."""
    from calc_solver.agents.planner import PlannerAgent
    import inspect
    sig = inspect.signature(PlannerAgent.plan)
    param = sig.parameters["problem"]
    # With `from __future__ import annotations`, type hints are strings
    ann = param.annotation
    assert ann is SolvingProblem or ann == "SolvingProblem"


def test_pipeline_passes_solving_problem_to_builder():
    """Verify type signature: BuilderAgent.build accepts SolvingProblem."""
    from calc_solver.agents.builder import BuilderAgent
    import inspect
    sig = inspect.signature(BuilderAgent.build)
    param = sig.parameters["problem"]
    ann = param.annotation
    assert ann is SolvingProblem or ann == "SolvingProblem"


def test_self_check_accepts_solving_problem():
    """self_check_answer should work with SolvingProblem (doesn't need gold)."""
    from calc_solver.agents.builder_self_check import self_check_answer
    import inspect
    sig = inspect.signature(self_check_answer)
    param = sig.parameters["problem"]
    ann = param.annotation
    assert ann is SolvingProblem or ann == "SolvingProblem"


# --- Prompt template scan tests ---

def _problem_with_gold() -> Problem:
    return Problem(
        problem_id="scan_test",
        question=r"Compute $\int 2x \, dx$",
        gold_answer=r"x^{2} + C",
        answer_type="expression",
        variable="x",
        metadata={"tag": {"have_indefinite": True}},
    )


def test_planner_prompt_excludes_gold():
    """Planner templates must not contain gold_answer."""
    p = _problem_with_gold()
    gold = p.gold_answer
    # Check system prompt
    system = get("planner", "system")
    assert gold.lower() not in system.lower()
    # Check user templates via format_prompt
    user = format_prompt("planner", "user_template",
                         question=p.question, answer_type=p.answer_type,
                         variable=p.variable, K=3)
    assert gold.lower() not in user.lower()
    replan = format_prompt("planner", "replan_template",
                           question=p.question, answer_type=p.answer_type,
                           variable=p.variable, K=3,
                           failed_strategies="power_rule")
    assert gold.lower() not in replan.lower()


def test_builder_prompt_excludes_gold():
    """Builder templates must not contain gold_answer."""
    p = _problem_with_gold()
    gold = p.gold_answer
    system = get("builder", "system")
    assert gold.lower() not in system.lower()
    user = format_prompt("builder", "user_template",
                         question=p.question, variable=p.variable,
                         strategy_name="power_rule",
                         strategy_rationale="Direct",
                         steps_outline="1. Integrate",
                         first_step="Integrate")
    assert gold.lower() not in user.lower()
    retry = format_prompt("builder", "retry_hint",
                          reason="failed", weak_step="step1")
    assert gold.lower() not in retry.lower()
