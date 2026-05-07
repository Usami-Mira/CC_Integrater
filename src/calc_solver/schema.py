from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class SolvingProblem(BaseModel):
    """Problem data available to solving agents (Planner, Builder).

    This type deliberately has NO gold_answer field. It is logically
    impossible for a function that only accepts SolvingProblem to see
    the correct answer.

    Created from a full Problem via SolvingProblem.from_problem(p).
    """

    problem_id: str
    question: str
    answer_type: Literal["expression", "value", "set", "interval"] = "expression"
    variable: str = "x"
    metadata: dict = Field(default_factory=dict)

    @classmethod
    def from_problem(cls, p: "Problem") -> "SolvingProblem":
        """Strip gold_answer — returns the safe subset for solving agents."""
        return cls(
            problem_id=p.problem_id,
            question=p.question,
            answer_type=p.answer_type,
            variable=p.variable,
            metadata=p.metadata,
        )


class Problem(BaseModel):
    """Full problem data including the gold answer — only for data loading
    and the Evaluator/Verifier grading stage."""

    problem_id: str
    question: str
    gold_answer: str
    answer_type: Literal["expression", "value", "set", "interval"] = "expression"
    variable: str = "x"
    metadata: dict = Field(default_factory=dict)


class Strategy(BaseModel):
    strategy_id: str
    name: str
    rationale: str
    steps_outline: list[str]


class StepTrace(BaseModel):
    step_no: int
    thought: str
    tool_call: Optional[dict] = None
    tool_result: Optional[str] = None
    state: Optional[str] = None


class Solution(BaseModel):
    strategy_id: str
    final_answer: str = ""
    final_answer_sympy: Optional[str] = None
    steps: list[StepTrace] = Field(default_factory=list)
    self_check_passed: bool = False
    error: Optional[str] = None


class EvalResult(BaseModel):
    problem_id: str
    chosen_strategy_id: Optional[str] = None
    final_answer: Optional[str] = None
    is_correct: bool = False
    confidence: float = 0.0
    method_agreement: int = 0
    candidates: list[Solution] = Field(default_factory=list)
    notes: str = ""
    loop_count: int = 0
