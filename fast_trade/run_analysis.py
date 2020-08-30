# TODO
import json
import pandas as pd
from datetime import timedelta


def analyze_df(df, strategy):
    in_trade = False
    last_base = float(strategy["base_balance"])
    commission = float(strategy["commission"])
    last_aux = 0.0
    last_fee = 0
    new_total_value = last_base

    tics = []
    for idx, row in df.iterrows():
        close = row.close
        curr_action = row.action
        fee = 0

        tic = {
            "date": idx,
            "aux":"",
            "base":"",
            "total_value": "",
            "in_trade": "",
            "fee":""
        }

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
        

        tic['aux'] = last_aux
        tic['base'] = last_base
        tic['total_value'] = new_total_value
        tic['in_trade'] = in_trade
        tic['fee'] = fee

        tics.append(tic)
    
    if strategy.get("exit_on_end") and in_trade:
        last_base = convert_aux_to_base(last_aux, close)
        last_aux = convert_base_to_aux(last_base, close)

        new_tic = {
            "date": idx+timedelta(minutes=1),
            "base": last_base,
            "total_value": last_base,
            "in_trade": False

        }
        tics.append(new_tic)



    tics = pd.DataFrame.from_dict(tics).set_index("date")
 
    df['aux'] = tics.aux
    df['base'] = tics.base
    df['total_value'] = tics.total_value
    df['in_trade'] = tics.in_trade
    df['fee'] = tics.fee


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
        return round((price/100) * commission, 8)
    
    return 0.0
