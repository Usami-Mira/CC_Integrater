from __future__ import annotations

from typing import TypedDict

import sympy as sp

from calc_solver.tools.latex_parser import best_parse


class ToolResult(TypedDict):
    ok: bool
    result: str
    error: str | None


def _ok(result: sp.Expr | str) -> ToolResult:
    return {"ok": True, "result": str(result), "error": None}


def _err(msg: str) -> ToolResult:
    return {"ok": False, "result": "", "error": msg}


def _sym(var: str) -> sp.Symbol:
    return sp.Symbol(var)


def parse(latex_or_expr: str, var: str = "x") -> ToolResult:
    expr = best_parse(latex_or_expr, var)
    if expr is None:
        return _err(f"Cannot parse: {latex_or_expr[:80]}")
    return _ok(expr)


def differentiate(expr_str: str, var: str = "x", n: int = 1) -> ToolResult:
    try:
        expr = best_parse(expr_str, var)
        if expr is None:
            return _err(f"Cannot parse: {expr_str[:80]}")
        result = sp.diff(expr, _sym(var), n)
        return _ok(result)
    except Exception as e:
        return _err(str(e))


def integrate_indef(expr_str: str, var: str = "x") -> ToolResult:
    try:
        expr = best_parse(expr_str, var)
        if expr is None:
            return _err(f"Cannot parse: {expr_str[:80]}")
        result = sp.integrate(expr, _sym(var))
        if isinstance(result, sp.Integral):
            return _err(f"SymPy could not evaluate integral: {result}")
        return _ok(result)
    except Exception as e:
        return _err(str(e))


def integrate_def(expr_str: str, var: str, a_str: str, b_str: str) -> ToolResult:
    try:
        expr = best_parse(expr_str, var)
        a = best_parse(a_str, var)
        b = best_parse(b_str, var)
        if expr is None:
            return _err(f"Cannot parse expr: {expr_str[:80]}")
        if a is None:
            return _err(f"Cannot parse lower bound: {a_str}")
        if b is None:
            return _err(f"Cannot parse upper bound: {b_str}")
        result = sp.integrate(expr, (_sym(var), a, b))
        if isinstance(result, sp.Integral):
            return _err(f"SymPy could not evaluate definite integral: {result}")
        return _ok(sp.simplify(result))
    except Exception as e:
        return _err(str(e))


def limit(expr_str: str, var: str, point_str: str, direction: str = "+-") -> ToolResult:
    try:
        expr = best_parse(expr_str, var)
        point = best_parse(point_str, var)
        if expr is None:
            return _err(f"Cannot parse: {expr_str[:80]}")
        if point is None:
            return _err(f"Cannot parse point: {point_str}")
        dir_map = {"+-": "+", "+": "+", "-": "-", "two": "+-"}
        sp_dir = dir_map.get(direction, "+")
        result = sp.limit(expr, _sym(var), point, dir=sp_dir)
        return _ok(result)
    except Exception as e:
        return _err(str(e))


def series(expr_str: str, var: str, point_str: str = "0", n: int = 6) -> ToolResult:
    try:
        expr = best_parse(expr_str, var)
        point = best_parse(point_str, var)
        if expr is None:
            return _err(f"Cannot parse: {expr_str[:80]}")
        if point is None:
            return _err(f"Cannot parse point: {point_str}")
        result = sp.series(expr, _sym(var), point, n).removeO()
        return _ok(result)
    except Exception as e:
        return _err(str(e))


def simplify(expr_str: str) -> ToolResult:
    try:
        expr = best_parse(expr_str)
        if expr is None:
            return _err(f"Cannot parse: {expr_str[:80]}")
        for f in [sp.simplify, sp.trigsimp, sp.cancel, sp.factor, sp.expand]:
            try:
                r = f(expr)
                if r is not None:
                    return _ok(r)
            except Exception:
                continue
        return _ok(expr)
    except Exception as e:
        return _err(str(e))


def solve(expr_str: str, var: str = "x") -> ToolResult:
    try:
        expr = best_parse(expr_str, var)
        if expr is None:
            return _err(f"Cannot parse: {expr_str[:80]}")
        result = sp.solve(expr, _sym(var))
        return _ok(result)
    except Exception as e:
        return _err(str(e))


def substitute(expr_str: str, mapping_str: str) -> ToolResult:
    """mapping_str like 'x=u+1' or 'x:u+1'."""
    try:
        expr = best_parse(expr_str)
        if expr is None:
            return _err(f"Cannot parse expr: {expr_str[:80]}")
        sep = "=" if "=" in mapping_str else ":"
        parts = mapping_str.split(sep, 1)
        if len(parts) != 2:
            return _err(f"Cannot parse mapping: {mapping_str}")
        old_sym = sp.Symbol(parts[0].strip())
        new_expr = best_parse(parts[1].strip())
        if new_expr is None:
            return _err(f"Cannot parse new expr: {parts[1]}")
        result = expr.subs(old_sym, new_expr)
        return _ok(sp.simplify(result))
    except Exception as e:
        return _err(str(e))


# Tool dispatch table for Builder
TOOL_REGISTRY: dict[str, object] = {
    "parse": parse,
    "differentiate": differentiate,
    "integrate_indef": integrate_indef,
    "integrate_def": integrate_def,
    "limit": limit,
    "series": series,
    "simplify": simplify,
    "solve": solve,
    "substitute": substitute,
}


def call_tool(name: str, args: dict) -> ToolResult:
    if name not in TOOL_REGISTRY:
        return _err(f"Unknown tool '{name}'. Available: {list(TOOL_REGISTRY.keys())}")
    try:
        fn = TOOL_REGISTRY[name]
        return fn(**args)
    except TypeError as e:
        return _err(f"Bad arguments for '{name}': {e}")
    except Exception as e:
        return _err(str(e))
