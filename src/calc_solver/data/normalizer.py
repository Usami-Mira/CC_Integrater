from __future__ import annotations

import re
import unicodedata


def clean_text(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    # BOM + zero-width chars
    text = text.lstrip("﻿")
    text = re.sub(r"[​‌‍﻿­]", "", text)
    # strip outer whitespace
    text = text.strip()
    # normalize full-width to half-width
    text = unicodedata.normalize("NFKC", text)
    # unify display fracs
    text = text.replace(r"\dfrac", r"\frac")
    text = text.replace(r"\tfrac", r"\frac")
    # \mathrm{d}x → dx
    text = re.sub(r"\\mathrm\{d\}", "d", text)
    # strip wrapping delimiters: $...$  \(...\)  \[...\]  [tex]...[/tex]
    text = _strip_outer_delimiters(text)
    return text.strip()


def _strip_outer_delimiters(text: str) -> str:
    patterns = [
        (r"^\$\$(.+)\$\$$", 1),
        (r"^\$(.+)\$$", 1),
        (r"^\\\[(.+)\\\]$", 1),
        (r"^\\\((.+)\\\)$", 1),
        (r"^\[tex\](.+)\[/tex\]$", 1),
        (r"^```latex\s*(.+)\s*```$", 1),
    ]
    for pat, grp in patterns:
        m = re.match(pat, text, re.DOTALL)
        if m:
            return m.group(grp).strip()
    return text


def infer_variable(question: str) -> str:
    """Return the most likely integration/differentiation variable."""
    keywords = {"e", "i", "pi", "d", "sin", "cos", "tan", "log", "ln", "lim", "C", "n", "k"}
    counts: dict[str, int] = {}
    for ch in re.findall(r"\b([a-zA-Z])\b", question):
        if ch not in keywords:
            counts[ch] = counts.get(ch, 0) + 1
    if not counts:
        return "x"
    return max(counts, key=lambda c: counts[c])


def infer_answer_type(answer: str) -> str:
    a = answer.strip()
    if re.search(r"[∪∩]|\\cup|\\cap", a):
        return "set"
    if re.search(r"\\left[\(\[].*,.*\\right[\)\]]", a):
        return "interval"
    if re.search(r"^\s*-?\d+(\.\d+)?\s*$", a):
        return "value"
    return "expression"
