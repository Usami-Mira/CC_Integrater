import pytest
from unittest.mock import AsyncMock, MagicMock
from calc_solver.agents.evaluator import EvaluatorAgent
from calc_solver.schema import Problem, Solution
from calc_solver.tools.verifier import Verifier


problem = Problem(
    problem_id="t1",
    question=r"\int x dx",
    gold_answer="x**2/2",
    variable="x",
    answer_type="expression",
)


def make_evaluator():
    client = MagicMock()
    client.chat = AsyncMock(return_value='{"best_id": "s1", "reason": "correct"}')
    verifier = Verifier(llm_client=None, llm_for_unsure=False)
    return EvaluatorAgent(client=client, verifier=verifier)


@pytest.mark.asyncio
async def test_one_correct():
    ev = make_evaluator()
    sols = [
        # x**2/2 + C should be equivalent to x**2/2 via derivative comparison
        Solution(strategy_id="s1", final_answer="x**2/2 + 3", self_check_passed=True),
        Solution(strategy_id="s2", final_answer="x**3", self_check_passed=False),
    ]
    result = await ev.evaluate(problem, sols)
    assert result.is_correct
    assert result.chosen_strategy_id == "s1"


@pytest.mark.asyncio
async def test_all_wrong():
    ev = make_evaluator()
    sols = [
        Solution(strategy_id="s1", final_answer="x**3", self_check_passed=False),
        Solution(strategy_id="s2", final_answer="x**4", self_check_passed=False),
    ]
    result = await ev.evaluate(problem, sols)
    assert not result.is_correct


@pytest.mark.asyncio
async def test_majority():
    ev = make_evaluator()
    sols = [
        Solution(strategy_id="s1", final_answer="x**3 + 1", self_check_passed=False),
        Solution(strategy_id="s2", final_answer="x**3 + 2", self_check_passed=False),
        Solution(strategy_id="s3", final_answer="x**3 + 1", self_check_passed=False),
    ]
    result = await ev.evaluate(problem, sols)
    assert not result.is_correct
    assert result.method_agreement >= 1
