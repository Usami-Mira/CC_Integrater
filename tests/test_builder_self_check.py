from calc_solver.agents.builder_self_check import self_check_answer
from calc_solver.schema import Problem, SolvingProblem


def test_self_check_indefinite_correct():
    """Derivative of answer matches integrand."""
    full_problem = Problem(
        problem_id="t1",
        question=r"\int x dx",
        gold_answer="x**2/2",
        variable="x",
        answer_type="expression",
        metadata={"tag": {"have_indefinite": True}},
    )
    problem = SolvingProblem.from_problem(full_problem)
    result = {"final_answer": "x**2/2", "final_answer_sympy": "x**2/2"}
    passed, reason = self_check_answer(result, problem)
    assert passed


def test_self_check_indefinite_wrong():
    """Wrong answer should fail self-check."""
    full_problem = Problem(
        problem_id="t1",
        question=r"\int x dx",
        gold_answer="x**2/2",
        variable="x",
        answer_type="expression",
        metadata={"tag": {"have_indefinite": True}},
    )
    problem = SolvingProblem.from_problem(full_problem)
    result = {"final_answer": "x**3", "final_answer_sympy": "x**3"}
    passed, reason = self_check_answer(result, problem)
    assert not passed


def test_self_check_empty_answer():
    """Empty answer should fail self-check."""
    full_problem = Problem(
        problem_id="t1",
        question=r"\int x dx",
        gold_answer="x**2/2",
        variable="x",
        answer_type="expression",
        metadata={"tag": {}},
    )
    problem = SolvingProblem.from_problem(full_problem)
    result = {"final_answer": "", "final_answer_sympy": ""}
    passed, reason = self_check_answer(result, problem)
    assert not passed
    assert "empty" in reason.lower()


def test_self_check_parseable_non_indefinite():
    """Parseable answer for non-indefinite should pass."""
    full_problem = Problem(
        problem_id="t1",
        question=r"Find the value of \int_0^1 x dx",
        gold_answer="1/2",
        variable="x",
        answer_type="value",
        metadata={"tag": {}},
    )
    problem = SolvingProblem.from_problem(full_problem)
    result = {"final_answer": "1/2", "final_answer_sympy": "1/2"}
    passed, reason = self_check_answer(result, problem)
    assert passed
