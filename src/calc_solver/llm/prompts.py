from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import yaml

_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is None:
        # When installed, configs/ is at the project root (sibling of src/)
        project_root = files("calc_solver").parent.parent
        p = project_root / "configs" / "prompts.yaml"
        if not p.exists():
            # Fallback for development: try relative to this file
            p = Path(__file__).parent.parent.parent.parent / "configs" / "prompts.yaml"
        _cache = yaml.safe_load(p.read_text(encoding="utf-8"))
    return _cache


def get(section: str, key: str) -> str:
    data = _load()
    return data[section][key]


def format_prompt(section: str, key: str, **kwargs: object) -> str:
    template = get(section, key)
    return template.format(**kwargs)
