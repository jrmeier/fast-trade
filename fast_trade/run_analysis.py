import pandas as pd
from datetime import timedelta


def apply_logic_to_df(df: pd.DataFrame, backtest: dict):
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



    """
    in_trade = False
    account_value = float(backtest.get("base_balance"))  #
    comission = float(backtest.get("comission"))
    lot_size = backtest.get("lot_size_perc")
    max_lot_size = backtest.get("max_lot_size")

    new_account_value = account_value

    aux = 0.0  #
    aux_list = []
    account_value_list = []
    in_trade_list = []
    fee_list = []
    adj_account_value_list = []

    for row in df.itertuples():
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

    if backtest.get("exit_on_end") and in_trade:
        # this means we should exit the trade
        [in_trade, aux, new_account_value, fee] = exit_position(
            account_value_list, close, aux, comission
        )
        new_date = df.index[-1] + timedelta(seconds=1)

        new_row = pd.DataFrame(data=[df.iloc[-1]], index=[new_date])

        df = df.append(pd.DataFrame(data=new_row))
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
