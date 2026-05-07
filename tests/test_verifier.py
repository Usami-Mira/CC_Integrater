from calc_solver.tools.verifier import Verifier


v = Verifier(llm_client=None, llm_for_unsure=False)


def test_string_equal():
    r = v.is_equivalent("\\sin x + C", "\\sin x + C", var="x")
    assert r.is_eq
    assert r.level_used == "L1"


def test_trig_identity():
    r = v.is_equivalent("sin(x)**2 + cos(x)**2", "1", var="x", answer_type="value")
    assert r.is_eq


def test_indefinite_integral_plus_c():
    # x^2/2 and x^2/2 + 5 should be equivalent for indefinite integrals
    r = v.is_equivalent("x**2/2 + 5", "x**2/2", var="x", answer_type="expression")
    assert r.is_eq


def test_different_answers():
    r = v.is_equivalent("x**2", "x**3", var="x", answer_type="expression")
    assert not r.is_eq


def test_numeric_value():
    r = v.is_equivalent("1/2", "0.5", var="x", answer_type="value")
    assert r.is_eq


def test_log_identity():
    r = v.is_equivalent("log(x) + log(2)", "log(2*x)", var="x", answer_type="expression")
    assert r.is_eq
