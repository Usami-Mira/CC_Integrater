from calc_solver.tools.verifier import Verifier
from calc_solver.tools.verifier.l1_string import check_string_equal
from calc_solver.tools.verifier.l2_symbolic import check_symbolic
from calc_solver.tools.verifier.l3_type_specific import check_type_specific
from calc_solver.tools.verifier.l4_numerical import check_numerical


v = Verifier(llm_client=None, llm_for_unsure=False)


# L1 tests
def test_l1_exact_match():
    assert check_string_equal("\\sin x + C", "\\sin x + C")


def test_l1_frac_variant():
    assert check_string_equal(r"\dfrac{1}{2}", r"\frac{1}{2}")


def test_l1_whitespace_insensitive():
    assert check_string_equal("x ** 2 + C", "x**2+C")


# L2 tests
def test_l2_trig_identity():
    from calc_solver.tools.latex_parser import best_parse
    pred = best_parse("sin(x)**2 + cos(x)**2", "x")
    gold = best_parse("1", "x")
    assert check_symbolic(pred, gold) is True


def test_l2_uncertain():
    from calc_solver.tools.latex_parser import best_parse
    pred = best_parse("x", "x")
    gold = best_parse("y", "x")
    # x - y cannot be simplified to 0, so L2 returns None (uncertain)
    assert check_symbolic(pred, gold) is None


# L3 tests
def test_l3_indefinite_integral_derivative_match():
    from calc_solver.tools.latex_parser import best_parse
    pred = best_parse("x**2/2 + 5", "x")
    gold = best_parse("x**2/2", "x")
    assert check_type_specific(pred, gold, "", "", "x", "expression") is True


def test_l3_numeric_value_match():
    from calc_solver.tools.latex_parser import best_parse
    pred = best_parse("1/2", "x")
    gold = best_parse("0.5", "x")
    assert check_type_specific(pred, gold, "", "", "x", "value") is True


# L4 tests
def test_l4_numeric_match():
    from calc_solver.tools.latex_parser import best_parse
    pred = best_parse("x**2", "x")
    gold = best_parse("x*x", "x")
    result, passed, total = check_numerical(pred, gold, "x", "expression", n_samples=10)
    assert result is True
    assert passed == total


def test_l4_numeric_mismatch():
    from calc_solver.tools.latex_parser import best_parse
    pred = best_parse("x**2", "x")
    gold = best_parse("x**3", "x")
    result, passed, total = check_numerical(pred, gold, "x", "expression", n_samples=10)
    assert result is False
