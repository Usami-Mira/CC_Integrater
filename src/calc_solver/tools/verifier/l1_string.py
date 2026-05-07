from __future__ import annotations

import re


def check_string_equal(pred: str, gold: str) -> bool:
    """L1: Normalized string comparison."""
    def norm(s: str) -> str:
        s = s.strip().replace(" ", "")
        s = s.rstrip(".;:,!?")
        s = s.replace(r"\dfrac", r"\frac").replace(r"\tfrac", r"\frac")
        s = re.sub(r"[\(\)\{\}]", lambda m: {"(": "[", ")": "]", "{": "[", "}": "]"}[m.group()], s)
        return s
    return norm(pred) == norm(gold)
