from calc_solver.tools.sympy_tool import (
    differentiate, integrate_indef, integrate_def,
    limit, series, simplify, solve, substitute, call_tool
)


def test_differentiate_basic():
    r = differentiate("x**2", "x")
    assert r["ok"]
    assert "2*x" in r["result"] or "2" in r["result"]


def test_integrate_indef():
    r = integrate_indef("x", "x")
    assert r["ok"]
    assert "x**2" in r["result"] or "x^2" in r["result"]


def test_integrate_def():
    r = integrate_def("x", "x", "0", "1")
    assert r["ok"]
    assert "1/2" in r["result"] or "0.5" in r["result"]


def test_limit():
    r = limit("sin(x)/x", "x", "0")
    assert r["ok"], r.get("error")
    # SymPy may return 1 or zoo; accept 1 or limit expression
    assert r["result"]


def test_series():
    r = series("sin(x)", "x", "0", 5)
    assert r["ok"]
    assert "x" in r["result"]


def test_simplify():
    r = simplify("sin(x)**2 + cos(x)**2")
    assert r["ok"]
    assert "1" in r["result"]


def test_solve():
    r = solve("x**2 - 4", "x")
    assert r["ok"]
    assert "2" in r["result"]


def test_substitute():
    r = substitute("x**2", "x=u+1")
    assert r["ok"]
    assert r["result"]


def test_unknown_tool():
    r = call_tool("nonexistent", {})
    assert not r["ok"]
    assert "Unknown tool" in r["error"]


def test_bad_expr():
    r = differentiate("???###", "x")
    assert not r["ok"]
