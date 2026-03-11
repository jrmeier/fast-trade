from datetime import timedelta
import numpy as np
import pandas as pd


ACTION_HOLD = 0
ACTION_ENTER = 1
ACTION_EXIT = 2


def _encode_actions(actions: np.ndarray) -> np.ndarray:
    codes = np.zeros(len(actions), dtype=np.int8)
    enter_mask = (actions == "e") | (actions == "ae")
    exit_mask = (actions == "x") | (actions == "ax") | (actions == "tsl")
    codes[enter_mask] = ACTION_ENTER
    codes[exit_mask] = ACTION_EXIT
    return codes


def _simulate_account_path(
    action_codes: np.ndarray,
    close_prices: np.ndarray,
    base_balance: float,
    comission: float,
    lot_size: float,
    max_lot_size: float,
    progress_callback=None,
):
    n = len(action_codes)
    in_trade_array = np.zeros(n, dtype=bool)
    account_value_array = np.zeros(n, dtype=float)
    aux_array = np.zeros(n, dtype=float)
    fee_array = np.zeros(n, dtype=float)

    fee_rate = comission / 100 if comission else 0.0
    in_trade = False
    cash_value = base_balance
    aux_value = 0.0
    update_every = max(1, n // 200) if n else 1

    for i in range(n):
        close = close_prices[i]
        fee = 0.0
        action_code = action_codes[i]

        if action_code == ACTION_ENTER and not in_trade:
            base_transaction_amount = cash_value * lot_size
            if max_lot_size and base_transaction_amount > max_lot_size:
                base_transaction_amount = max_lot_size

            aux_value = round(base_transaction_amount / close, 8) if base_transaction_amount else 0.0
            fee = round(aux_value * fee_rate, 8) if fee_rate and aux_value else 0.0
            aux_value = aux_value - fee
            cash_value = round(cash_value - base_transaction_amount, 8)
            in_trade = True

        elif action_code == ACTION_EXIT and in_trade:
            base_value = round(aux_value * close, 8) if aux_value else 0.0
            fee = round(base_value * fee_rate, 8) if fee_rate and base_value else 0.0
            cash_value = round(cash_value + base_value - fee, 8)
            aux_value = 0.0
            in_trade = False

        account_value_array[i] = cash_value
        aux_array[i] = aux_value
        in_trade_array[i] = in_trade
        fee_array[i] = fee
        if progress_callback and (i % update_every == 0 or i == n - 1):
            progress_callback({"percent": int((i + 1) / n * 100)})

    adj_account_value_array = account_value_array + np.round(aux_array * close_prices, 8)
    return {
        "in_trade": in_trade_array,
        "account_value": account_value_array,
        "aux": aux_array,
        "fee": fee_array,
        "adj_account_value": adj_account_value_array,
    }


def apply_logic_to_df(df: pd.DataFrame, backtest: dict, progress_callback=None):
    """Analyzes the dataframe and runs sort of a market simulation, entering and exiting positions

    Parameters
    ----------
        df, dataframe from process_dataframe after the actions have been added
        backtest: dict, contains instructions on when to enter/exit trades

    Returns
    -------
        df, returns a dataframe with the new rows processed

    Explainer
    ---------
    This is one of more complex parts of the library. I'm going to try to explain what's going on here.
    Fast Trade uses what's known as "vectorized" backtesting. This is what makes Fast Trade fast. To do that all the
    calculations (datapoints/indicators) are made before this step and all the actions have been generated,
    meaning based on the datapoints alone, the action is determined.(see process_logic_and_action in run_backtest.py).


    At this point, the state of backtest is as follows:
        * datapoints/indicators ARE calculated
        * actions (enter, exit) ARE determined

    What is left is to apply the strategy to our dataframe so we can analyze the perfomance of our strategy. To do this,
    we need to keep track of our account balance and transactions.

    This optimized version uses vectorized operations where possible for better performance.
    """
    # Try to use vectorized operations for better performance
    try:
        base_balance = float(backtest.get("base_balance"))
        comission = float(backtest.get("comission"))
        lot_size = backtest.get("lot_size_perc")
        max_lot_size = backtest.get("max_lot_size")

        # Get action and close price arrays
        actions = df["action"].values
        close_prices = df["close"].values
        action_codes = _encode_actions(actions)
        sim = _simulate_account_path(
            action_codes=action_codes,
            close_prices=close_prices,
            base_balance=base_balance,
            comission=comission,
            lot_size=lot_size,
            max_lot_size=max_lot_size,
            progress_callback=progress_callback,
        )
        fee_rate = comission / 100 if comission else 0.0
        in_trade_array = sim["in_trade"]
        account_value_array = sim["account_value"]
        aux_array = sim["aux"]
        fee_array = sim["fee"]
        adj_account_value_array = sim["adj_account_value"]

        # Handle exit_on_end if needed
        if backtest.get("exit_on_end") and in_trade_array[-1]:
            # Create a new row for the exit
            new_date = df.index[-1] + timedelta(seconds=1)
            new_row = pd.DataFrame(data=[df.iloc[-1]], index=[new_date])

            # Process the exit
            close = close_prices[-1]
            new_base = round(aux_array[-1] * close, 8) if aux_array[-1] else 0.0
            fee = round(new_base * fee_rate, 8) if fee_rate and new_base else 0.0
            new_account_value = account_value_array[-1] + new_base - fee

            # Add the new row to the dataframe
            df = pd.concat([df, pd.DataFrame(data=new_row)])

            # Append values to arrays
            in_trade_array = np.append(in_trade_array, False)
            aux_array = np.append(aux_array, 0.0)
            account_value_array = np.append(account_value_array, new_account_value)
            fee_array = np.append(fee_array, fee)
            adj_account_value = new_account_value + convert_aux_to_base(0.0, close)
            adj_account_value_array = np.append(
                adj_account_value_array, adj_account_value
            )

        # Add columns to dataframe
        df["aux"] = aux_array
        df["account_value"] = account_value_array
        df["adj_account_value"] = adj_account_value_array
        df["in_trade"] = in_trade_array
        df["fee"] = fee_array

    except Exception:
        # Fall back to original implementation if vectorized approach fails
        in_trade = False
        account_value = float(backtest.get("base_balance"))
        comission = float(backtest.get("comission"))
        lot_size = backtest.get("lot_size_perc")
        max_lot_size = backtest.get("max_lot_size")

        new_account_value = account_value

        aux = 0.0
        aux_list = []
        account_value_list = []
        in_trade_list = []
        fee_list = []
        adj_account_value_list = []

        total_rows = len(df)
        update_every = max(1, total_rows // 200)
        for idx, row in enumerate(df.itertuples()):
            close = row.close
            curr_action = row.action
            fee = 0.0

            if curr_action in ["e", "ae"] and not in_trade:
                # this means we should enter the trade
                [in_trade, aux, new_account_value, fee] = enter_position(
                    account_value_list,
                    lot_size,
                    account_value,
                    max_lot_size,
                    close,
                    comission,
                )

            if curr_action in ["x", "ax", "tsl"] and in_trade:
                # this means we should exit the trade

                [in_trade, aux, new_account_value, fee] = exit_position(
                    account_value_list, close, aux, comission
                )

            adj_account_value = new_account_value + convert_aux_to_base(aux, close)

            aux_list.append(aux)
            account_value_list.append(new_account_value)
            in_trade_list.append(in_trade)
            fee_list.append(fee)
            adj_account_value_list.append(adj_account_value)
            if progress_callback and (
                idx % update_every == 0 or idx == total_rows - 1
            ):
                progress_callback({"percent": int((idx + 1) / total_rows * 100)})

        if backtest.get("exit_on_end") and in_trade:
            # this means we should exit the trade
            [in_trade, aux, new_account_value, fee] = exit_position(
                account_value_list, close, aux, comission
            )
            new_date = df.index[-1] + timedelta(seconds=1)

            new_row = pd.DataFrame(data=[df.iloc[-1]], index=[new_date])

            df = pd.concat([df, pd.DataFrame(data=new_row)])
            aux_list.append(fee)

            account_value_list.append(new_account_value)
            in_trade_list.append(in_trade)
            fee_list.append(fee)
            adj_account_value = new_account_value + convert_aux_to_base(aux, close)

            adj_account_value_list.append(adj_account_value)

        df["aux"] = aux_list
        df["account_value"] = account_value_list
        df["adj_account_value"] = adj_account_value_list
        df["in_trade"] = in_trade_list
        df["fee"] = fee_list

    return df


def enter_position(
    account_value_list, lot_size, account_value, max_lot_size, close, comission
):
    # Since the first trade could happen right away, we have to give the account
    # some value, since its not yet appended to the account_value_list.
    if len(account_value_list):
        base_transaction_amount = account_value_list[-1] * lot_size
    else:
        base_transaction_amount = account_value * lot_size

    # limit the transaction amount so we don't trade too much
    if max_lot_size and base_transaction_amount > max_lot_size:
        base_transaction_amount = max_lot_size

    new_aux = convert_base_to_aux(base_transaction_amount, close)
    fee = calculate_fee(new_aux, comission)

    new_aux = new_aux - fee

    new_account_value = calculate_new_account_value_on_enter(
        base_transaction_amount, account_value_list, account_value
    )

    in_trade = True

    return [in_trade, new_aux, new_account_value, fee]


def exit_position(account_value_list, close, new_aux, comission):
    # this means we should EXIT the trade
    new_base = convert_aux_to_base(new_aux, close)
    fee = calculate_fee(new_base, comission)
    new_base = new_base - fee

    new_account_value = account_value_list[-1] + new_base

    new_aux = 0  # since we "converted" the auxilary values back to the base

    in_trade = False

    return [in_trade, new_aux, new_account_value, fee]


def convert_base_to_aux(new_base: float, close: float):
    """converts the base coin to the aux coin
    Parameters
    ----------
        new_base, the last amount maintained by the backtest
        close, the closing price of the coin

    Returns
    -------
        float, amount of the last base divided by the closing price
    """
    if new_base:
        return round(new_base / close, 8)
    return 0.0


def convert_aux_to_base(new_aux: float, close: float):
    """converts the aux coin to the base coin
    Parameters
    ----------
        new_base, the last amount maintained by the backtest
        close, the closing price of the coin
    Returns
    -------
        float, amount of the last aux divided by the closing price
    """
    if new_aux:
        return round(new_aux * close, 8)
    return 0.0


def calculate_fee(order_size: float, comission: float):
    """calculates the trading fees from the exchange
    Parameters
    ----------
        order_size, amount of the coin after the transaction
        comission, percentage of the transaction
    """
    if comission:
        return round((order_size / 100) * comission, 8)

    return 0.0


def calculate_new_account_value_on_enter(
    base_transaction_amount, account_value_list, account_value
):
    """calulates the new account value after the transaction"""

    # assuming we can spend 100% of our base_transaction_amount
    # TODO: add slippage calulations

    if len(account_value_list):
        new_account_value = account_value_list[-1] - base_transaction_amount
    else:
        new_account_value = account_value - base_transaction_amount
    return round(new_account_value, 8)
