import datetime
import pprint
import typing

from fast_trade.archive import binance_api, coinbase_api

from .db_helpers import get_local_assets
from .update_kline import update_kline


def get_assets(exchange: str = "local") -> typing.List[str]:
    assets = []
    try:
        if exchange == "binanceus":
            assets.extend(binance_api.get_available_symbols())
        elif exchange == "binancecom":
            assets.extend(binance_api.get_available_symbols(tld="com"))
        elif exchange == "coinbase":
            assets.extend(coinbase_api.get_asset_ids())
        elif exchange == "local":
            assets.extend(get_local_assets())
        else:
            raise ValueError(f"Exchange {exchange} not supported")
        assets.sort()
    except Exception as e:
        print(f"Error getting assets for {exchange}: {e}")
        raise e

    pprint.pprint(assets)
    print(f"Found {len(assets)} assets for {exchange}")
    return assets


def download_asset(
    symbol: str,
    exchange: str,
    start: typing.Union[str, datetime.datetime] = datetime.datetime.now()
    - datetime.timedelta(days=30),
    end: typing.Union[str, datetime.datetime] = datetime.datetime.now(),
):
    """
    Download a single asset from the given exchange

    Args:
        symbol (str): The symbol to download
        exchange (str): The exchange to download from
        start (str | datetime.datetime): The start date to download from. Defaults to 30 days ago Must be in
        UTC timezone and isoformat.
        end (str | datetime.datetime): The end date to download to. Defaults to now. Must be in UTC timezone
        and isoformat.
    """
    # default to 30 days ago
    if not isinstance(start, datetime.datetime):
        start = datetime.datetime.fromisoformat(start)
    if not isinstance(end, datetime.datetime):
        end = datetime.datetime.fromisoformat(end)

    # set the timezone to utc
    start = start.replace(tzinfo=datetime.timezone.utc)
    end = end.replace(tzinfo=datetime.timezone.utc)
    # make sure the symbol exists

    if exchange == "binanceus":
        # make sure the symbol exists
        if symbol not in binance_api.get_available_symbols():
            raise ValueError(f"Symbol {symbol} not found on Binance US")
        db_path = update_kline(symbol, exchange, start, end)
    elif exchange == "binancecom":
        if symbol not in binance_api.get_available_symbols(tld="com"):
            raise ValueError(f"Symbol {symbol} not found on Binance COM")
        db_path = update_kline(symbol, exchange, start, end)
    elif exchange == "coinbase":
        if symbol not in coinbase_api.get_asset_ids():
            raise ValueError(f"Symbol {symbol} not found on Coinbase")
        db_path = update_kline(symbol, exchange, start, end)
    else:
        raise ValueError(f"Exchange {exchange} not supported")

    print(f"Downloaded {symbol} from {exchange} to {db_path}")
    return db_path
