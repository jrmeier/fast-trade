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


def test_validate_basic_invalid():
    mock_backtest = {
        "base_balance": "c1000",
        "freq": "1Min22",
    }

    backtest_mirror = validate_backtest(mock_backtest)

    assert backtest_mirror["base_balance"].get("error") is True
    assert backtest_mirror["freq"].get("error") is True


def test_validate_data_points_valid():
    mock_datapoints = [
        {"args": [30], "transformer": "sma", "name": "sma_short"},
    ]

    mock_backtest = {"datapoints": mock_datapoints}

    backtest_mirror = validate_backtest(mock_backtest)

    assert backtest_mirror["datapoints"] is None


def test_validate_data_points_invalid():
    mock_datapoints = [
        {"args": [30], "transformer": "fake_news_transformer", "name": "sma_short"},
    ]

    mock_backtest = {"datapoints": mock_datapoints}

    backtest_mirror = validate_backtest(mock_backtest)

    assert backtest_mirror["datapoints"].get("error") is True


def test_validate_data_points_invalid_name():
    mock_datapoints = [
        {"args": [30], "transformer": "ema", "name": ""},
    ]

    mock_backtest = {"datapoints": mock_datapoints}

    backtest_mirror = validate_backtest(mock_backtest)

    assert backtest_mirror["datapoints"].get("error") is True


def test_validate_enter_logic_valid():
    mock_datapoints = [
        {"args": [30], "transformer": "sma", "name": "sma_short"},
    ]

    mock_enter_logic = [["close", ">", "sma_short"]]

    mock_backtest = {"datapoints": mock_datapoints, "enter": mock_enter_logic}

    backtest_mirror = validate_backtest(mock_backtest)

    assert backtest_mirror["datapoints"] is None


def test_validate_enter_logic_invalid_1():
    mock_datapoints = [
        {"args": [30], "transformer": "sma", "name": "sma_short"},
    ]

    mock_enter_logic = [["close", ">", "sma_shortee"]]

    mock_backtest = {"datapoints": mock_datapoints, "enter": mock_enter_logic}

    backtest_mirror = validate_backtest(mock_backtest)

    assert backtest_mirror["enter"].get("error") is True


def test_validate_start_is_optional():
    mock_backtest = {
        "any_enter": [],
        "any_exit": [],
        "datapoints": [{"args": [9], "transformer": "sma", "name": "sma_short"}],
        "enter": [["close", ">", "sma_short"]],
        "exit": [["close", "<", "sma_short"]],
    }

    backtest_mirror = validate_backtest(mock_backtest)

    assert backtest_mirror.get("has_error") is False
    assert backtest_mirror["start"] is None


def test_validate_deprecated_start_date_message_spelling():
    mock_backtest = {
        "any_enter": [],
        "any_exit": [],
        "datapoints": [{"args": [9], "transformer": "sma", "name": "sma_short"}],
        "enter": [["close", ">", "sma_short"]],
        "exit": [["close", "<", "sma_short"]],
        "start_date": "2025-12-01",
    }

    backtest_mirror = validate_backtest(mock_backtest)

    assert backtest_mirror["start_date"]["error"] is True
    msg = backtest_mirror["start_date"]["msgs"][0]
    assert "Paramater" not in msg
    assert 'Parameter "start_date" is deprecated' in msg


def test_validate_any_enter_logic_valid():
    mock_datapoints = [
        {"args": [30], "transformer": "sma", "name": "sma_short"},
    ]

    mock_any_enter_logic = [["close", ">", "sma_short"]]

    mock_backtest = {"datapoints": mock_datapoints, "any_enter": mock_any_enter_logic}

    backtest_mirror = validate_backtest(mock_backtest)

    assert backtest_mirror["datapoints"] is None


def test_validate_any_enter_logic_invalid_1():
    mock_datapoints = [
        {"args": [30], "transformer": "sma", "name": "sma_shorter"},
    ]

    mock_enter_logic = [["close", ">", "sma_short"]]

    mock_backtest = {"datapoints": mock_datapoints, "any_enter": mock_enter_logic}

    backtest_mirror = validate_backtest(mock_backtest)

    assert backtest_mirror["any_enter"].get("error") is True


def test_validate_exit_logic_valid():
    mock_datapoints = [
        {"args": [30], "transformer": "sma", "name": "sma_short"},
    ]

    mock_any_exit_logic = [["close", ">", "sma_short"]]

    mock_backtest = {
        "datapoints": mock_datapoints,
        "enter": [],
        "exit": mock_any_exit_logic,
    }

    backtest_mirror = validate_backtest(mock_backtest)

    assert backtest_mirror["exit"] is None


def test_validate_exit_logic_invalid_1():
    mock_datapoints = [
        {"args": [30], "transformer": "sma", "name": "sma_shorter"},
    ]

    mock_enter_logic = [["close", ">", "sma_short"]]

    mock_backtest = {
        "datapoints": mock_datapoints,
        "enter": [],
        "exit": mock_enter_logic,
    }

    backtest_mirror = validate_backtest(mock_backtest)
    print(backtest_mirror)

    assert backtest_mirror["exit"].get("error") is True


def test_validate_any_exit_logic_valid():
    mock_datapoints = [
        {"args": [30], "transformer": "sma", "name": "sma_short"},
    ]

    mock_any_exit_logic = [["close", ">", "sma_short"]]

    mock_backtest = {
        "datapoints": mock_datapoints,
        "enter": [],
        "any_exit": mock_any_exit_logic,
    }

    backtest_mirror = validate_backtest(mock_backtest)

    assert backtest_mirror["any_exit"] is None


def test_validate_any_exit_logic_invalid_1():
    mock_datapoints = [
        {"args": [30], "transformer": "sma", "name": "wtf"},
    ]

    mock_exit_logic = [["close", ">", "no name here"]]

    mock_backtest = {
        "datapoints": mock_datapoints,
        "exit": [],
        "enter": [],
        "any_exit": mock_exit_logic,
    }

    backtest_mirror = validate_backtest(mock_backtest)

    print(backtest_mirror)

    assert backtest_mirror["any_exit"].get("error") is True
