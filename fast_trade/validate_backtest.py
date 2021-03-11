

def validate_backtest(backtest):
    """ validates a backtest object and returns errors/warnings

    Parameters
    -----------
        backtest, user constructed backtest object

    Returns
    -------
        tuple, [errors, warnings], returns a tuple with any
        errors and warnings, respectively
    """

    errors = []
    warnings = []

    # first validate the basic stuff
    base_balance = backtest.get("base_balance")
    if not base_balance:
        warnings.push("Setting \"base_balance\" is not set.")
    exit_on_end = backtest.get("exit_on_end", True)
    if not exit_on_end:
        warnings.push("Setting \"exit_on_end\" is not set.")
    commission = backtest.get("commission", 0)
    if not commission:
        warnings.push("Setting \"commission\" is not set.")
    trailing_stop_loss = backtest.get("trailing_stop_loss", 0)
    if not trailing_stop_loss:
        warnings.push("Setting \"trailing_stop_loss\" is not set.")

    exit_logic = backtest.get("exit", [])
    if not len(exit_logic):
        warnings.push("No exit logic set.")

    enter_logic = backtest.get("enter", [])
    if not len(enter_logic):
        warnings.push("No enter logic set.")

    indicators = backtest.get("indicators", [])
    # now check the logic fields to the data points
    if not len(indicators):
        warnings.push("No indicators set.")
