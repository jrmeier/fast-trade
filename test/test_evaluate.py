import pytest

from fast_trade.evaluate import (
    evaluate_rules,
    handle_rule,
)


def test_handle_rule_all_operators():
    result = {"return_perc": 12.5, "num_trades": 4.0, "nested": {"value": 3.0}}
    assert handle_rule(result, ["return_perc", ">", 10]) is True
    assert handle_rule(result, ["return_perc", "<", 20]) is True
    assert handle_rule(result, ["return_perc", ">=", 12.5]) is True
    assert handle_rule(result, ["return_perc", "<=", 12.5]) is True
    assert handle_rule(result, ["return_perc", ">", 50]) is False
    assert handle_rule(result, ["nested.value", ">", 2]) is True
    assert handle_rule(result, ["num_trades", ">", "return_perc"]) is False


def test_handle_rule_unknown_operator_returns_false():
    assert handle_rule({"x": 1.0}, ["x", "==", 1]) is False


def test_evaluate_rules_empty_and_success():
    assert evaluate_rules({"a": 1}, []) == (False, False, [])
    rules = [["return_perc", ">", 5], ["return_perc", "<", 20]]
    result = {"return_perc": 10.0}
    all_ok, any_ok, res = evaluate_rules(result, rules)
    assert all_ok is True
    assert any_ok is True
    assert res == [True, True]


def test_evaluate_rules_rejects_missing_key_after_passing_rule():
    rules = [["return_perc", ">", 0], ["missing.key", ">", 1]]
    with pytest.raises(KeyError, match="missing"):
        evaluate_rules({"return_perc": 1.0}, rules)


def test_evaluate_rules_rejects_malformed_rule():
    with pytest.raises(IndexError):
        evaluate_rules({"return_perc": 1.0}, [["return_perc"]])


def test_evaluate_main_block_runs(capsys):
    import runpy

    runpy.run_module("fast_trade.evaluate", run_name="__main__")
    captured = capsys.readouterr()
    assert "False" in captured.out or "False" in captured.err
