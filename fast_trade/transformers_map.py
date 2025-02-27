from .finta import TA

"""
These are all the datapoints the can be used in a backtest as a "transformer".
Any function can be implimented as an transformer.
"""
transformers_map = {
    "sma": TA.SMA,
    "smm": TA.SMM,
    "ssma": TA.SSMA,
    "ema": TA.EMA,
    "dema": TA.DEMA,
    "tema": TA.TEMA,
    "trima": TA.TRIMA,
    "vama": TA.VAMA,
    "er": TA.ER,
    "kama": TA.KAMA,
    "zlema": TA.ZLEMA,
    "wma": TA.WMA,
    "hma": TA.HMA,
    "evwma": TA.EVWMA,
    "vwap": TA.VWAP,
    "smma": TA.SMMA,
    "macd": TA.MACD,
    "ppo": TA.PPO,
    "vw_macd": TA.VW_MACD,
    "ev_macd": TA.EV_MACD,
    "mom": TA.MOM,
    "roc": TA.ROC,
    "rsi": TA.RSI,
    "ift_rsi": TA.IFT_RSI,
    "tr": TA.TR,
    "atr": TA.ATR,
    "sar": TA.SAR,
    "bbands": TA.BBANDS,
    "bbwidth": TA.BBWIDTH,
    "percent_b": TA.PERCENT_B,
    "kc": TA.KC,
    "do": TA.DO,
    "dmi": TA.DMI,
    "adx": TA.ADX,
    "pivot": TA.PIVOT,
    "pivot_fib": TA.PIVOT_FIB,
    "stoch": TA.STOCH,
    "stochd": TA.STOCHD,
    "stochrsi": TA.STOCHRSI,
    "williams": TA.WILLIAMS,
    "uo": TA.UO,
    "ao": TA.AO,
    "mi": TA.MI,
    "vortex": TA.VORTEX,
    "kst": TA.KST,
    "tsi": TA.TSI,
    "tp": TA.TP,
    "adl": TA.ADL,
    "chaikin": TA.CHAIKIN,
    "mfi": TA.MFI,
    "obv": TA.OBV,
    "wobv": TA.WOBV,
    "vzo": TA.VZO,
    "pzo": TA.PZO,
    "efi": TA.EFI,
    "cfi": TA.CFI,
    "ebbp": TA.EBBP,
    "emv": TA.EMV,
    "cci": TA.CCI,
    "copp": TA.COPP,
    "basp": TA.BASP,
    "baspn": TA.BASPN,
    "cmo": TA.CMO,
    "chandelier": TA.CHANDELIER,
    "qstick": TA.QSTICK,
    "tmf": TA.TMF,
    "fish": TA.FISH,
    "ichimoku": TA.ICHIMOKU,
    "apz": TA.APZ,
    "sqzmi": TA.SQZMI,
    "vpt": TA.VPT,
    "fve": TA.FVE,
    "vfi": TA.VFI,
    "msd": TA.MSD,
    "wto": TA.WTO,
    "rolling_min": TA.ROLLING_MIN,
    "rolling_max": TA.ROLLING_MAX,
}
