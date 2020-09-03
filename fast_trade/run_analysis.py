import pandas as pd
from datetime import timedelta


def analyze_df(df: pd.DataFrame, strategy: dict):
    """Analyzes the dataframe and runs sort of a market simulation, entering and exiting positions

    Parameters
    ----------
        df, dataframe from process_dataframe after the actions have been added
        strategy: dict, contains instructions on when to enter/exit trades

    Returns
    -------
        df, returns a dataframe with the new rows processed
    """
    in_trade = False
    last_base = float(strategy["base_balance"])
    commission = float(strategy["commission"])
    last_aux = 0.0
    new_total_value = last_base

    aux_list = []
    base_list = []
    total_value_list = []
    in_trade_list = []
    fee_list = []

    for row in df.itertuples():
        close = row.close
        curr_action = row.action
        fee = 0

        if curr_action == "e" and not in_trade:
            # this means we should enter the trade
            last_aux = convert_base_to_aux(last_base, close)
            fee = calculate_fee(last_aux, commission)

            last_aux = last_aux - fee
            new_total_value = convert_aux_to_base(last_aux, close)

            # should be extremely close to 0
            last_base = round(last_base - new_total_value, 8)
            in_trade = True

        if curr_action == "x" and in_trade:
            last_base = convert_aux_to_base(last_aux, close)
            fee = calculate_fee(last_base, commission)
            last_base = last_base - fee
            last_aux = convert_base_to_aux(last_base, close)
            new_total_value = last_base

            in_trade = False

        aux_list.append(last_aux)
        base_list.append(last_base)
        total_value_list.append(new_total_value)
        in_trade_list.append(in_trade)
        fee_list.append(fee)

    if strategy.get("exit_on_end") and in_trade:
        last_base = convert_aux_to_base(last_aux, close)
        last_aux = convert_base_to_aux(last_base, close)
        new_date = df.index[-1] + timedelta(minutes=1)

        df = df.append(pd.DataFrame(index=[new_date]))

        aux_list.append(last_aux)
        base_list.append(last_base)
        total_value_list.append(new_total_value)
        in_trade_list.append(in_trade)
        fee_list.append(False)

    df["aux"] = aux_list
    df["base"] = base_list
    df["total_value"] = total_value_list
    df["in_trade"] = in_trade_list
    df["fee"] = fee_list

    return df


def convert_base_to_aux(last_base: float, close: float):
    """converts the base coin to the aux coin
    Parameters
    ----------
        last_base, the last amount maintained by the strat
        close, the closing price of the coin

    Returns
    -------
        float, amount of the last base divided by the closing price
    """
    if last_base:
        return round(last_base / close, 8)
    return 0.0


def convert_aux_to_base(last_aux: float, close: float):
    """converts the aux coin to the base coin
    Parameters
    ----------
        last_base, the last amount maintained by the strat
        close, the closing price of the coin
    Returns
    -------
        float, amount of the last aux divided by the closing price
    """
    if last_aux:
        return round(last_aux * close, 8)
    return 0.0


def calculate_fee(price: float, commission: float):
    """calculates the trading fees from the exchange
    Parameters
    ----------
        price, amount of the coin after the transaction
        commission, percentage of the transaction
    """
    if commission:
        return round((price / 100) * commission, 8)

    return 0.0
