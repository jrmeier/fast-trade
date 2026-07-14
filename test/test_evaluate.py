import pytest

from fast_trade.evaluate import (
    evaluate_rules,
    extract_error_messages,
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


def test_evaluate_rules_exception_is_printed_and_skipped(capsys):
    rules = [["missing.key", ">", 1]]
    all_ok, any_ok, res = evaluate_rules({"return_perc": 1.0}, rules)
    captured = capsys.readouterr()
    assert "missing" in captured.out or "KeyError" in captured.out
    assert all_ok is False
    assert any_ok is False
    assert res == []


def test_extract_error_messages_nested_and_non_string():
    error_dict = {
        "enter": {
            "msgs": ["plain", {"nested": {"msgs": [42]}}, 99],
        },
        "list": [{"msgs": ["from list"]}],
    }
    text = extract_error_messages(error_dict)
    assert "plain" in text
    assert "99" in text
    assert "from list" in text


def test_evaluate_main_block_runs(capsys):
    import runpy

    runpy.run_module("fast_trade.evaluate", run_name="__main__")
    captured = capsys.readouterr()
    assert "False" in captured.out or "False" in captured.err
