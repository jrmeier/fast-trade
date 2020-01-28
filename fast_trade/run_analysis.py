def analyze_log(df, base_balance):
    in_trade = False
    column_map = list(df.columns)
    close_column_idx = column_map.index("close")
    action_col_idx = column_map.index("actions")

    aux_balance = 0

    aux_log = []
    base_log = []
    for row in df.values:
        close = row[close_column_idx]
        if row[action_col_idx] == "e" and not in_trade:
            # enter the trade
            aux_balance = enter_trade(close, base_balance)
            in_trade = True

        if row[action_col_idx] == "x" and in_trade:
            base_balance = exit_trade(close, aux_balance)
            in_trade = False

        aux_log.append(aux_balance)
        base_log.append(base_balance)
    return aux_log, base_log


def enter_trade(close, base_balance):
    """ returns new aux balance """
    if base_balance and close:
        return round(float(base_balance) / float(close), 8)
    return 0.0


def exit_trade(close, aux_balance):
    """ return new base balance """
    if aux_balance and close:
        return round(float(aux_balance) * float(close), 8)
    return 0.0
