import pytest
from pathlib import Path
from calc_solver.data.loader import _match_column, load_parquet


def test_match_exact():
    assert _match_column(["question", "answer", "id"], ["question"]) == "question"


def test_match_case_insensitive():
    assert _match_column(["Question", "Answer"], ["question"]) == "Question"


def test_match_contains():
    assert _match_column(["gold_answer_latex"], ["gold_answer"]) == "gold_answer_latex"


def test_match_missing():
    assert _match_column(["foo", "bar"], ["question"]) is None


def test_load_real_parquet():
    parquet_path = "data/raw/question-v1(2).parquet"
    if not Path(parquet_path).exists():
        pytest.skip("parquet not found")
    problems = load_parquet(parquet_path, max_rows=10)
    assert len(problems) > 0
    p = problems[0]
    assert p.question
    assert p.gold_answer
    assert p.problem_id
