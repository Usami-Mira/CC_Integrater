from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from calc_solver.schema import Problem
from calc_solver.data.normalizer import clean_text, infer_variable, infer_answer_type

CANDIDATES: dict[str, list[str]] = {
    "question": ["question", "problem", "query", "prompt", "input", "题目", "问题", "stem", "题干", "content"],
    "gold_answer": ["answer", "gold", "gold_answer", "label", "target", "solution", "标准答案", "答案", "output", "ground_truth"],
    "problem_id": ["id", "problem_id", "qid", "uid", "index", "编号"],
    "answer_type": ["type", "answer_type", "category", "题型"],
    "variable": ["variable", "var", "主变量"],
    "tag": ["tag", "tags", "metadata"],
}


def _match_column(df_cols: list[str], targets: list[str]) -> str | None:
    lower = {c.lower().strip(): c for c in df_cols}
    for t in targets:
        if t.lower() in lower:
            return lower[t.lower()]
    for t in targets:
        for low, orig in lower.items():
            if t.lower() in low:
                return orig
    for t in targets:
        matches = difflib.get_close_matches(t.lower(), lower.keys(), n=1, cutoff=0.85)
        if matches:
            return lower[matches[0]]
    return None


def load_parquet(
    path: str,
    column_overrides: dict[str, str] | None = None,
    max_rows: int | None = None,
) -> list[Problem]:
    df = pd.read_parquet(path)
    if max_rows:
        df = df.head(max_rows)

    mapping = {k: _match_column(list(df.columns), v) for k, v in CANDIDATES.items()}
    if column_overrides:
        mapping.update(column_overrides)

    missing = [k for k in ("question", "gold_answer") if mapping.get(k) is None]
    if missing:
        raise ValueError(
            f"Required fields not matched: {missing}\n"
            f"Actual columns: {list(df.columns)}\n"
            f"Run: python scripts/inspect_parquet.py {path}\n"
            f"Then set data.column_overrides in configs/config.yaml."
        )

    problems: list[Problem] = []
    rejected: list[dict] = []

    for i, row in df.iterrows():
        try:
            p = _row_to_problem(row, mapping, fallback_id=f"row_{i}")
            problems.append(p)
        except ValueError as e:
            rejected.append({"row": int(i), "reason": str(e)})

    out_dir = Path("data/processed")
    out_dir.mkdir(parents=True, exist_ok=True)
    _dump_jsonl(problems, out_dir / "problems.jsonl")
    (out_dir / "_load_report.json").write_text(
        json.dumps({"kept": len(problems), "rejected_count": len(rejected), "rejected": rejected[:50]},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return problems


def _row_to_problem(row: Any, mapping: dict[str, str | None], fallback_id: str) -> Problem:
    q_raw = row[mapping["question"]]
    a_raw = row[mapping["gold_answer"]]

    q = clean_text(str(q_raw)) if q_raw is not None else ""
    a = clean_text(str(a_raw)) if a_raw is not None else ""

    pid_col = mapping.get("problem_id")
    pid = str(row[pid_col]) if pid_col else fallback_id

    # lenient filtering: only reject truly empty/garbage rows
    if not q or len(q) < 2:
        raise ValueError("question_too_short")
    if not a:
        raise ValueError("empty_gold_answer")
    if len(q) > 12000:
        raise ValueError("question_too_long")
    if _looks_like_image_only(q):
        raise ValueError("image_only_problem")

    # extract tag metadata if present
    tag_col = mapping.get("tag")
    tag_data: dict = {}
    if tag_col and tag_col in row.index:
        raw_tag = row[tag_col]
        if isinstance(raw_tag, dict):
            tag_data = raw_tag
        elif isinstance(raw_tag, str):
            try:
                tag_data = json.loads(raw_tag)
            except Exception:
                pass

    # infer answer_type from tag if available, else from answer text
    answer_type = _infer_answer_type_from_tag(tag_data) or infer_answer_type(a)
    variable = infer_variable(q)

    return Problem(
        problem_id=pid,
        question=q,
        gold_answer=a,
        answer_type=answer_type,
        variable=variable,
        metadata={
            "tag": _sanitize(tag_data),
            "source": str(row.get("source", "")) if "source" in row.index else "",
        },
    )


def _sanitize(obj: Any) -> Any:
    """Recursively convert numpy/exotic types to plain Python for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    # numpy scalar check without importing numpy at module level
    type_name = type(obj).__module__
    if type_name == "numpy" or (hasattr(obj, "item") and callable(obj.item)):
        try:
            return obj.item()
        except Exception:
            return str(obj)
    return obj


def _looks_like_image_only(text: str) -> bool:
    patterns = ["<image>", "base64,", "[image]", "data:image"]
    t = text.lower()
    return any(p in t for p in patterns) and len(text) < 200


def _infer_answer_type_from_tag(tag: dict) -> str | None:
    pt = tag.get("problem_type", "")
    if pt in ("set", "interval"):
        return pt
    return None


def _dump_jsonl(problems: list[Problem], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for p in problems:
            f.write(p.model_dump_json() + "\n")
