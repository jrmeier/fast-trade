from fast_trade.validate_backtest import validate_backtest


def test_validate_backtest_empty_1():
    mock_backtest = {}

    backtest_mirror = validate_backtest(mock_backtest)

    assert backtest_mirror["datapoints"]["error"] is True
    assert backtest_mirror["exit"]["error"] is True
    assert backtest_mirror["enter"]["error"] is True


def test_validate_backtest_base_balance():
    mock_backtest = {"base_balance": 1000}
    backtest_mirror = validate_backtest(mock_backtest)
    assert backtest_mirror["base_balance"] is None

    mock_backtest = {"base_balance": "1000"}
    backtest_mirror = validate_backtest(mock_backtest)
    assert backtest_mirror["base_balance"] is None

    mock_backtest = {"base_balance": "1000.0"}
    backtest_mirror = validate_backtest(mock_backtest)
    assert backtest_mirror["base_balance"] is None

    mock_backtest = {"base_balance": 1000.0}
    backtest_mirror = validate_backtest(mock_backtest)
    assert backtest_mirror["base_balance"] is None


# def test_validate_basic_invalid():
#     mock_backtest = {
#         "base_balance": "c1000",
#         "chart_period": "1Min22",
#         "chart_stop": "x1615515979",
#         "chart_start": "x1583979979",
#         "comission": "0.011",
#         "exit_on_end": "true"
#     }

#     backtest_mirror = validate_backtest(mock_backtest)

#     assert backtest_mirror["base_balance"].get("error") is True
#     assert backtest_mirror["chart_period"].get("error") is True
#     assert backtest_mirror["chart_stop"].get("error") is True
#     assert backtest_mirror["chart_start"].get("error") is True
#     assert backtest_mirror["comission"].get("error") is True
#     assert backtest_mirror["exit_on_end"].get("error") is True
