import re
import sympy as sp

try:
    from latex2sympy2 import latex2sympy as l2s
except ImportError:
    l2s = None


def parse_latex(latex: str) -> sp.Expr | None:
    """Parse LaTeX string to SymPy expression using latex2sympy2."""
    latex = re.sub(r"\s*[+\-]\s*C\b", "", latex, flags=re.IGNORECASE).strip()
    if l2s is not None:
        try:
            return l2s(latex)
        except Exception:
            pass
    try:
        return sp.sympify(latex, evaluate=True)
    except Exception:
        return None


def parse_expr(text: str, var: str = "x") -> sp.Expr | None:
    try:
        local_dict = {var: sp.Symbol(var)}
        return sp.sympify(text, locals=local_dict, evaluate=True)
    except Exception:
        return None


def best_parse(text: str, var: str = "x") -> sp.Expr | None:
    text = text.strip()
    text = re.sub(r"\s*[+\-]\s*C\b", "", text, flags=re.IGNORECASE).strip()
    if "\\" in text or "^" in text or "{" in text:
        expr = parse_latex(text)
        if expr is not None:
            return expr
    expr = parse_expr(text, var)
    if expr is not None:
        return expr
    return parse_latex(text)
