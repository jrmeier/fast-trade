import pandas as pd
from datetime import timedelta


def analyze_df(df, strategy):
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

        new_tic = pd.DataFrame(
            {
                "date": row.index.iloc[-1].dt + timedelta(minutes=1),
                "base": last_base,
                "total_value": last_base,
                "in_trade": False,
            },
            index=["date"],
        )
        print(new_tic)

        df = df.append(new_tic)

        # aux_list.append(last_aux)
        # base_list.append(last_base)
        # total_value_list.append(new_total_value)
        # in_trade_list.append(in_trade)
        # fee_list.append(False)

    df["aux"] = aux_list
    df["base"] = base_list
    df["total_value"] = total_value_list
    df["in_trade"] = in_trade_list
    df["fee"] = fee_list

    return df


def convert_base_to_aux(last_base, close):
    """ returns new aux balance """
    if last_base:
        return round(last_base / close, 8)


def convert_aux_to_base(last_aux, close):
    """ returns new base balance """
    if last_aux:
        return round(last_aux * close, 8)
    return 0.0


def calculate_fee(price, commission):
    """ determines the trading fees from the exchange """
    if commission:
        return round((price / 100) * commission, 8)

    return 0.0
