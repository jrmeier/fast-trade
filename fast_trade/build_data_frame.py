import pandas as pd
from finta import TA
import os
import re
from datetime import datetime
import time

def build_data_frame(ohlcv_path, indicators=[], timerange={}):
    """
    Params:
        ohlcv_path: string, absolute path of where to find the data file
        indicators: list of objects, assembles and calulates all the data
    """
    if not os.path.isfile(ohlcv_path):
        raise Exception(f"File doesn't exist: {ohlcv_path}")

    df = pd.read_csv(ohlcv_path)

    df = df[df.close != 0]
    
    df['Datetime'] = pd.to_datetime(df['date'], unit='s')
    df.set_index(['Datetime'], inplace=True )
    df.sort_index(inplace=True)

    if len(timerange.keys()):
        start_dt = timerange['start']
        stop_dt = timerange['stop']
        
        df = df.loc[start_dt:stop_dt]


    for ind in indicators:
        timeperiod = determine_chart_period(str(ind.get("timeperiod")))
        func = ind.get("func")
        field_name = ind.get("name")
        df[field_name] = indicator_map[func](df, timeperiod)

    # df = df[df.close != 0]
    
    # df['Datetime'] = pd.to_datetime(df['date'], unit='s')
    # df.set_index(['Datetime'], inplace=True )
    # df.sort_index(inplace=True)

    # if len(timerange.keys()):
    #     start_dt = timerange['start']
    #     stop_dt = timerange['stop']
        
    #     return df.loc[start_dt:stop_dt]

    return df

def determine_chart_period(chartperiod_str):
    if "m" in chartperiod_str:
        return int(chartperiod_str.replace("m", ""))

    if "h" in chartperiod_str:
        clean_chartperiod = chartperiod_str.replace("h", "")
        return int(clean_chartperiod) * 60

    if "d" in chartperiod_str:
        clean_chartperiod = chartperiod_str.replace("d", "")
        return int(clean_chartperiod) * 1440

    return int(chartperiod_str)




indicator_map = {
    "ta.sma": TA.SMA,
    "ta.smm": TA.SMM,
    "ta.ssma": TA.SSMA,
    "ta.ema": TA.EMA,
    "ta.dema": TA.DEMA,
    "ta.tema": TA.TEMA,
    "ta.trima": TA.TRIMA,
    "ta.vama": TA.VAMA,
    "ta.er": TA.ER,
    "ta.kama": TA.KAMA,
    "ta.zlema": TA.ZLEMA,
    "ta.wma": TA.WMA,
    "ta.hma": TA.HMA,
    "ta.evwma": TA.EVWMA,
    "ta.vwap": TA.VWAP,
    "ta.smma": TA.SMMA,
    "ta.macd": TA.MACD,
    "ta.ppo": TA.PPO,
    "ta.vw_macd": TA.VW_MACD,
    "ta.ev_macd": TA.EV_MACD,
    "ta.mom": TA.MOM,
    "ta.roc": TA.ROC,
    "ta.rsi": TA.RSI,
    "ta.ift_rsi": TA.IFT_RSI,
    "ta.tr": TA.TR,
    "ta.atr": TA.ATR,
    "ta.sar": TA.SAR,
    "ta.bbands": TA.BBANDS,
    "ta.bbwidth": TA.BBWIDTH,
    "ta.percent_b": TA.PERCENT_B,
    "ta.kc": TA.KC,
    "ta.do": TA.DO,
    "ta.dmi": TA.DMI,
    "ta.adx": TA.ADX,
    "ta.pivot": TA.PIVOT,
    "ta.pivot_fib": TA.PIVOT_FIB,
    "ta.stoch": TA.STOCH,
    "ta.stochd": TA.STOCHD,
    "ta.stochrsi": TA.STOCHRSI,
    "ta.williams": TA.WILLIAMS,
    "ta.uo": TA.UO,
    "ta.ao": TA.AO,
    "ta.mi": TA.MI,
    "ta.vortex": TA.VORTEX,
    "ta.kst": TA.KST,
    "ta.tsi": TA.TSI,
    "ta.tp": TA.TP,
    "ta.adl": TA.ADL,
    "ta.chaikin": TA.CHAIKIN,
    "ta.mfi": TA.MFI,
    "ta.obv": TA.OBV,
    "ta.wobv": TA.WOBV,
    "ta.vzo": TA.VZO,
    "ta.pzo": TA.PZO,
    "ta.efi": TA.EFI,
    "ta.cfi": TA.CFI,
    "ta.ebbp": TA.EBBP,
    "ta.emv": TA.EMV,
    "ta.cci": TA.CCI,
    "ta.copp": TA.COPP,
    "ta.basp": TA.BASP,
    "ta.baspn": TA.BASPN,
    "ta.cmo": TA.CMO,
    "ta.chandelier": TA.CHANDELIER,
    "ta.qstick": TA.QSTICK,
    "ta.tmf": TA.TMF,
    "ta.wto": TA.WTO,
    "ta.fish": TA.FISH,
    "ta.ichimoku": TA.ICHIMOKU,
    "ta.apz": TA.APZ,
    "ta.vr": TA.VR,
    "ta.sqzmi": TA.SQZMI,
    "ta.vpt": TA.VPT,
    "ta.fve": TA.FVE,
    "ta.vfi": TA.VFI,
    "ta.msd": TA.MSD,
}
