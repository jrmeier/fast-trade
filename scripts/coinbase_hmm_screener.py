#!/usr/bin/env python3
"""Thin wrapper around the productized Coinbase HMM screener."""

from __future__ import annotations

import argparse
from pathlib import Path

from fast_trade.ml.hmm_data import screen_from_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Coinbase USD-market HMM forecast screener.")
    parser.add_argument("--product", action="append", dest="products", help="Coinbase product id.")
    parser.add_argument("--max-products", type=int, default=40)
    parser.add_argument("--lookback-days", type=int, default=260)
    parser.add_argument("--horizon", action="append", dest="horizons", type=int)
    parser.add_argument("--states", type=int, default=3)
    parser.add_argument("--simulations", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cache-dir", type=Path, default=Path("ft_archive/screen_cache/coinbase"))
    parser.add_argument("--cache-max-age-hours", type=float, default=6.0)
    parser.add_argument("--json-out", type=Path, default=Path("ft_archive/screens/coinbase_hmm.json"))
    parser.add_argument("--md-out", type=Path, default=Path("ft_archive/screens/coinbase_hmm.md"))
    parser.add_argument("--min-candles", type=int, default=180)
    parser.add_argument("--min-quote-volume-24h", type=float, default=3_000_000)
    parser.add_argument("--min-avg-quote-volume-30d", type=float, default=3_000_000)
    parser.add_argument("--max-drawdown-60d", type=float, default=-0.45)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    horizons = tuple(sorted(set(args.horizons or [7, 30, 60])))
    config = {
        "exchange": "coinbase",
        "symbols": list(args.products or []),
        "live": True,
        "settings": {
            "lookback_days": args.lookback_days,
            "horizons": list(horizons),
            "states": args.states,
            "simulations": args.simulations,
            "seed": args.seed,
            "max_products": args.max_products,
            "cache_dir": str(args.cache_dir),
            "cache_max_age_hours": args.cache_max_age_hours,
        },
        "filters": {
            "min_candles": args.min_candles,
            "min_quote_volume_24h": args.min_quote_volume_24h,
            "min_avg_quote_volume_30d": args.min_avg_quote_volume_30d,
            "max_drawdown_60d": args.max_drawdown_60d,
        },
        "outputs": {
            "title": "Coinbase HMM Screener",
            "json_out": str(args.json_out),
            "md_out": str(args.md_out),
        },
    }
    payload = screen_from_config(config)
    print(f"Wrote {args.md_out}")
    print(f"Wrote {args.json_out}")
    print(f"Screened {len(payload['results'])} market(s), skipped {len(payload['skipped'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
