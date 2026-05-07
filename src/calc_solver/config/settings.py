from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    provider: str = "dashscope"
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model_id: str = "qwen-plus"
    timeout_s: int = 60
    temperatures: dict[str, float] = Field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str) -> "ModelConfig":
        from yaml import safe_load

        data = safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(**data)

    def temperature_for(self, agent: str) -> float:
        """Get temperature for a specific agent role."""
        return self.temperatures.get(agent, 0.2)
