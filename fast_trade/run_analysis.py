def analyze_df(df, strategy):
    in_trade = False
    column_map = list(df.columns)
    close_column_idx = column_map.index("close")
    action_col_idx = column_map.index("actions")

    base_balance = strategy["base_balance"]

    aux_balance = 0.0

    aux_log = []
    base_log = []

    smooth_base = []
    for idx, row in enumerate(df.values):
        close = row[close_column_idx]
        if row[action_col_idx] == "e" and not in_trade:
            aux_balance = enter_trade(close, base_balance)

            tmp_base_balance = exit_trade(close, aux_balance)
            base_balance = 0
            in_trade = True

        if row[action_col_idx] == "x" and in_trade:
            base_balance = exit_trade(close, aux_balance)
            aux_balance = 0
            in_trade = False

        if base_balance:
            smooth_base.append(base_balance)
        else:
            smooth_base.append(tmp_base_balance)

        aux_log.append(aux_balance)
        base_log.append(base_balance)

    if in_trade and strategy["exit_on_end"]:
        close = df.values[-1][close_column_idx]
        base_balance = exit_trade(close, aux_balance)
        smooth_base.append(base_balance)
        aux_balance = 0
        aux_log.append(aux_balance)
        base_log.append(base_balance)

    return aux_log, base_log, smooth_base


def enter_trade(close, base_balance):
    """ returns new aux balance """
    if base_balance:
        return round(base_balance / close, 8)
    return 0.0


def exit_trade(close, aux_balance):
    """ returns new base balance """
    if aux_balance:
        return round(aux_balance * close, 8)
    return 0.0
