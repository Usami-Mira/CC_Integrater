"""
Usage: python scripts/run_batch.py --parquet data/raw/xxx.parquet --K 3 [--max-rows 50]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import yaml
from dotenv import load_dotenv  # type: ignore[import]

load_dotenv()


def _sanitize_run_id(s: str) -> str:
    """Remove/replace characters invalid for Windows filenames."""
    s = re.sub(r'[<>:"/\\|?*{}\[\] ,]', '_', s)
    s = re.sub(r'_+', '_', s)
    return s.strip('_.')[:100] if len(s) > 100 else s


def build_pipeline(cfg: dict, model_cfg: dict, run_id: str):
    from calc_solver.agents.builder import BuilderAgent
    from calc_solver.agents.evaluator import EvaluatorAgent
    from calc_solver.agents.planner import PlannerAgent
    from calc_solver.llm.client import QwenClient
    from calc_solver.orchestrator.pipeline import Pipeline
    from calc_solver.tools.verifier import Verifier
    from calc_solver.utils.logger import RunLogger

    logger = RunLogger(run_id, log_dir=cfg["paths"]["log_dir"])

    client = QwenClient(
        model_id=model_cfg["model_id"],
        base_url=model_cfg["base_url"],
        timeout_s=model_cfg["timeout_s"],
        max_concurrent=cfg["rate_limits"]["max_concurrent_llm_calls"],
        logger=logger,
    )

    planner = PlannerAgent(client=client, logger=logger)
    builder = BuilderAgent(
        client=client,
        max_steps=cfg["run"]["builder_max_steps"],
        max_retries=cfg["run"]["builder_max_retries"],
        logger=logger,
    )
    verifier = Verifier(
        llm_client=client,
        n_samples=cfg["verifier"]["n_samples"],
        llm_for_unsure=cfg["verifier"]["llm_for_unsure"],
        logger=logger,
    )
    evaluator = EvaluatorAgent(client=client, verifier=verifier, logger=logger)

    pipeline = Pipeline(
        planner=planner,
        builder=builder,
        evaluator=evaluator,
        K=cfg["run"]["K"],
        max_outer_loops=cfg["run"]["max_outer_loops"],
        problem_concurrency=cfg["run"]["problem_concurrency"],
        builder_concurrency_per_problem=cfg["run"]["builder_concurrency_per_problem"],
        enable_replan_on_fail=cfg["run"]["enable_replan_on_fail"],
        logger=logger,
    )
    return pipeline, logger


def load_resume_ids(log_dir: str, run_id: str) -> set[str]:
    pipeline_log = Path(log_dir) / run_id / "pipeline.jsonl"
    ids: set[str] = set()
    if pipeline_log.exists():
        for line in pipeline_log.read_text(encoding="utf-8").splitlines():
            try:
                ids.add(json.loads(line)["problem_id"])
            except Exception:
                pass
    return ids


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", required=True)
    parser.add_argument("--K", type=int, default=3)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--run-id", type=str, default=None)
    parser.add_argument("--config", type=str, default="configs/config.yaml")
    parser.add_argument("--model-config", type=str, default="configs/model.yaml")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    with open(args.model_config, "r", encoding="utf-8") as f:
        model_cfg = yaml.safe_load(f)

    if args.K:
        cfg["run"]["K"] = args.K

    run_id = args.run_id
    if not run_id:
        run_id = cfg["paths"].get("default_run_id")
    if not run_id:
        stem = Path(args.parquet).stem
        cfg_parts = [f"K{cfg['run'].get('K', 3)}"]
        if cfg['run'].get('max_retries_per_strategy'):
            cfg_parts.append(f"r{cfg['run']['max_retries_per_strategy']}")
        cfg_str = '-'.join(cfg_parts)
        run_id = f"{stem}-{cfg_str}"

    run_id = _sanitize_run_id(run_id)

    print(f"Run ID: {run_id}")

    from calc_solver.data.loader import load_parquet
    overrides = cfg["data"].get("column_overrides") or {}
    problems = load_parquet(args.parquet, column_overrides=overrides or None, max_rows=args.max_rows)
    print(f"Loaded {len(problems)} problems from {args.parquet}")

    resume_ids = load_resume_ids(cfg["paths"]["log_dir"], run_id)
    if resume_ids:
        print(f"Resuming: {len(resume_ids)} already done, skipping.")

    pipeline, logger = build_pipeline(cfg, model_cfg, run_id)

    try:
        results = await pipeline.run_batch(problems, resume_ids=resume_ids)
    finally:
        logger.close()

    correct = sum(1 for r in results if r.is_correct)
    total = len([r for r in results if r.notes != "skipped_resume"])
    if total:
        print(f"\nAccuracy: {correct}/{total} = {correct/total:.1%}")
    else:
        print("No results")
    print(f"Logs: logs/{run_id}/")

    from analyze_results import summarize
    summarize(f"logs/{run_id}")


if __name__ == "__main__":
    asyncio.run(main())
