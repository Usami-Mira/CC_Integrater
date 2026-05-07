from __future__ import annotations

import json
import logging
from pathlib import Path


class RunLogger:
    def __init__(self, run_id: str, log_dir: str = "logs"):
        self.run_id = run_id
        self.run_dir = Path(log_dir) / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "traces").mkdir(exist_ok=True)

        self._pipeline_f = open(self.run_dir / "pipeline.jsonl", "a", encoding="utf-8")
        self._llm_f = open(self.run_dir / "llm_calls.jsonl", "a", encoding="utf-8")

        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        self._log = logging.getLogger(f"calc_solver.{run_id}")

    def info(self, msg: str, **kw: object) -> None:
        self._log.info(msg + (" " + str(kw) if kw else ""))

    def error(self, msg: str, **kw: object) -> None:
        self._log.error(msg + (" " + str(kw) if kw else ""))

    def warning(self, msg: str, **kw: object) -> None:
        self._log.warning(msg + (" " + str(kw) if kw else ""))

    def log_pipeline(self, record: dict) -> None:
        self._pipeline_f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        self._pipeline_f.flush()

    def log_llm(self, record: dict) -> None:
        self._llm_f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        self._llm_f.flush()

    def log_llm_verbose(self, record: dict) -> None:
        import os
        if os.environ.get("LOG_LLM_VERBOSE", "").lower() in ("1", "true", "yes"):
            path = self.run_dir / "llm_verbose.jsonl"
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def log_trace(self, problem_id: str, data: dict) -> None:
        path = self.run_dir / "traces" / f"{problem_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    def close(self) -> None:
        self._pipeline_f.close()
        self._llm_f.close()
