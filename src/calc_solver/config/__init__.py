from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from calc_solver.config.settings import ModelConfig


class RunConfig(BaseModel):
    K: int = 3
    builder_max_steps: int = 12
    builder_max_retries: int = 2
    max_outer_loops: int = 2
    enable_replan_on_fail: bool = True
    enable_early_stop: bool = False
    problem_concurrency: int = 4
    builder_concurrency_per_problem: int = 3
    max_retries_per_strategy: int = 2


class VerifierConfig(BaseModel):
    n_samples: int = 30
    llm_for_unsure: bool = True


class DataConfig(BaseModel):
    column_overrides: dict[str, str] = Field(default_factory=dict)
    drop_metadata_columns: list[str] = Field(default_factory=list)
    max_question_chars: int = 12000


class PathsConfig(BaseModel):
    parquet_dir: str = "data/raw"
    log_dir: str = "logs"


class AppConfig(BaseModel):
    """Typed configuration loaded from config.yaml."""

    run: RunConfig = Field(default_factory=RunConfig)
    rate_limits: dict[str, Any] = Field(default_factory=dict)
    data: DataConfig = Field(default_factory=DataConfig)
    verifier: VerifierConfig = Field(default_factory=VerifierConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)

    @classmethod
    def from_yaml(cls, path: str) -> "AppConfig":
        data = _load_yaml(Path(path))
        return cls(**data)


def _load_yaml(path: Path) -> dict:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8"))


__all__ = ["AppConfig", "DataConfig", "ModelConfig", "PathsConfig", "RunConfig", "VerifierConfig"]
