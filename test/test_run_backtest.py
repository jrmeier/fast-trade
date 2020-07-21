from fast_trade import take_action, determine_action


def test_take_action_greater_than():
    mock_strategy = [["close", ">", "short"]]
    mock_row = [1523937963, 0.0212, 0.01, 0.025, 0.01, 36898, 0.0112]
    mock_columns = ["date", "close", "open", "high", "low", "volume", "short"]

    res = take_action(mock_row, mock_strategy, mock_columns)
    assert res == True


def test_take_action_less_than():
    mock_strategy = [["close", "<", "short"]]
    mock_row = [1523937963, 0.0212, 0.01, 0.025, 0.01, 36898, 0.0112]
    mock_columns = ["date", "close", "open", "high", "low", "volume", "short"]

    res = take_action(mock_row, mock_strategy, mock_columns)
    assert res == False


def test_take_action_equal():
    mock_strategy = [["close", "=", "short"]]
    mock_row = [1523937963, 0.0212, 0.01, 0.025, 0.01, 36898, 0.0212]
    mock_columns = ["date", "close", "open", "high", "low", "volume", "short"]

    res = take_action(mock_row, mock_strategy, mock_columns)
    assert res == True
