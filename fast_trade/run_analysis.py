def analyze_df(df, base_balance):
    in_trade = False
    column_map = list(df.columns)
    close_column_idx = column_map.index("close")
    action_col_idx = column_map.index("actions")

    aux_balance = 0

    aux_log = []
    base_log = []
    total_trades = 0
    for row in df.values:
        close = row[close_column_idx]
        if row[action_col_idx] == "e" and not in_trade:
            aux_balance = enter_trade(close, base_balance)
            base_balance = 0
            in_trade = True
            total_trades += 1

        if row[action_col_idx] == "x" and in_trade:
            base_balance = exit_trade(close, aux_balance)
            aux_balance = 0
            in_trade = False
            total_trades += 1

        aux_log.append(aux_balance)
        base_log.append(base_balance)
    return aux_log, base_log, total_trades


def enter_trade(close, base_balance):
    """ returns new aux balance """
    if base_balance:
        return round(float(base_balance) / float(close), 8)
    return 0.0


def exit_trade(close, aux_balance):
    """ returns new base balance """
    if aux_balance:
        return round(float(aux_balance) * float(close), 8)
    return 0.0
