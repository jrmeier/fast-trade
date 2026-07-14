import numpy as np
import pandas as pd

from fast_trade.ml.hmm_screen import (
    evaluate_filters,
    fit_hmm_forecast,
    format_markdown,
    make_features,
    normalize_config,
    run_hmm_screen,
    write_screen_reports,
)


def _synthetic_ohlcv(rows: int = 220, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=rows, freq="D", tz="UTC")
    rets = rng.normal(0.001, 0.02, size=rows)
    close = 100 * np.cumprod(1.0 + rets)
    high = close * (1.0 + rng.uniform(0.0, 0.01, size=rows))
    low = close * (1.0 - rng.uniform(0.0, 0.01, size=rows))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    volume = rng.uniform(1_000, 5_000, size=rows)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def test_normalize_config_defaults():
    cfg = normalize_config({})
    assert cfg["exchange"] == "coinbase"
    assert cfg["settings"]["horizons"] == (7, 30, 60)
    assert cfg["live"] is False


def test_make_features_and_fit_hmm_forecast():
    df = _synthetic_ohlcv()
    features = make_features(df)
    assert list(features.columns) == ["ret", "vol", "range", "trend", "drawdown"]
    result = fit_hmm_forecast(
        "BTC-USD",
        df,
        meta={"exchange": "coinbase", "price": float(df["close"].iloc[-1])},
        horizons=(7, 30),
        n_states=2,
        simulations=50,
        seed=1,
    )
    assert result["symbol"] == "BTC-USD"
    assert "7" in result["forecasts"]
    assert "30" in result["forecasts"]
    assert isinstance(result["score"], float)


def test_evaluate_filters_rejects_short_history():
    df = _synthetic_ohlcv(rows=50)
    ok, reason = evaluate_filters(df, {}, {"min_candles": 180})
    assert ok is False
    assert "candles" in reason


def test_run_hmm_screen_ranks_and_skips(tmp_path):
    good = _synthetic_ohlcv(rows=220, seed=1)
    bad = _synthetic_ohlcv(rows=40, seed=2)
    payload = run_hmm_screen(
        {
            "exchange": "coinbase",
            "settings": {"horizons": [7, 30], "states": 2, "simulations": 40, "seed": 3},
            "filters": {"min_candles": 180, "max_drawdown_60d": -1.0},
        },
        [
            {"symbol": "AAA-USD", "exchange": "coinbase", "df": good, "meta": {"price": 10.0}},
            {"symbol": "BBB-USD", "exchange": "coinbase", "df": bad, "meta": {}},
            {
                "symbol": "CCC-USD",
                "exchange": "coinbase",
                "df": pd.DataFrame(),
                "meta": {"load_error": "missing archive"},
            },
        ],
    )
    assert len(payload["results"]) == 1
    assert payload["results"][0]["symbol"] == "AAA-USD"
    skipped_symbols = {row["symbol"] for row in payload["skipped"]}
    assert skipped_symbols == {"BBB-USD", "CCC-USD"}
    assert any("missing archive" in row["reason"] for row in payload["skipped"])

    json_out = tmp_path / "out.json"
    md_out = tmp_path / "out.md"
    written = write_screen_reports(payload, str(json_out), str(md_out), title="Test Screen")
    assert written["json_out"]
    assert "Test Screen" in format_markdown(payload, title="Test Screen")
    assert md_out.read_text(encoding="utf-8").startswith("# Test Screen")


def test_screen_from_config_uses_loader(monkeypatch, tmp_path):
    from fast_trade.ml import hmm_data

    df = _synthetic_ohlcv(rows=220, seed=9)

    def fake_load_universe(config):
        return [
            {
                "symbol": "BTC-USD",
                "exchange": "coinbase",
                "df": df,
                "meta": {"exchange": "coinbase", "price": float(df["close"].iloc[-1])},
            }
        ]

    monkeypatch.setattr(hmm_data, "load_universe", fake_load_universe)
    out_json = tmp_path / "screen.json"
    payload = hmm_data.screen_from_config(
        {
            "exchange": "coinbase",
            "settings": {"simulations": 30, "states": 2, "horizons": [7, 30]},
            "outputs": {"json_out": str(out_json), "title": "Unit Screen"},
        }
    )
    assert len(payload["results"]) == 1
    assert out_json.exists()


def test_mcp_hmm_screen_forwards(monkeypatch):
    import fast_trade.mcp_server as mcp_server
    import fast_trade.ml.hmm_data as hmm_data

    captured = {}

    def fake_screen_from_config(config):
        captured["config"] = config
        return {"results": [{"symbol": "BTC-USD", "score": 1.0}], "skipped": []}

    monkeypatch.setattr(hmm_data, "screen_from_config", fake_screen_from_config)

    result = mcp_server.hmm_screen(
        exchange="coinbase",
        symbols=["BTC-USD"],
        live=False,
        simulations=25,
        horizons=[7, 30],
    )
    assert result["results"][0]["symbol"] == "BTC-USD"
    assert captured["config"]["symbols"] == ["BTC-USD"]
    assert captured["config"]["settings"]["simulations"] == 25
