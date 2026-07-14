import numpy as np
import pandas as pd
import pytest

from fast_trade.ml.hmm_screen import (
    avg_quote_volume,
    evaluate_filters,
    fit_hmm_forecast,
    format_markdown,
    make_features,
    max_drawdown,
    money,
    normalize_config,
    run_hmm_screen,
    simulate_returns,
    write_screen_reports,
)
from hmmlearn.hmm import GaussianHMM


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

    cfg_scalar = normalize_config({"settings": {"horizons": 30}})
    assert cfg_scalar["settings"]["horizons"] == (7, 30, 60)


def test_empty_helpers_and_money():
    empty = pd.DataFrame(columns=["close", "volume"])
    assert max_drawdown(empty, 60) == 0.0
    assert avg_quote_volume(empty, 30) == 0.0
    assert money(2_500_000_000) == "$2.50B"
    assert money(2_500_000) == "$2.5M"
    assert money(2_500) == "$2.5K"
    assert money(25.5) == "$25.50"


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


def test_simulate_returns_fallback_paths():
    model = GaussianHMM(n_components=2, covariance_type="diag", n_iter=10, random_state=1)
    x = np.random.default_rng(0).normal(size=(120, 1))
    model.fit(x)
    model.transmat_ = np.array([[0.0, 0.0], [np.nan, np.nan]])
    states = np.zeros(120, dtype=int)
    returns = pd.Series(np.random.default_rng(1).normal(0, 0.01, size=120))
    out = simulate_returns(model, states, returns, [7], simulations=5, rng=np.random.default_rng(2))
    assert "p50" in out[7]

    model.transmat_ = np.array([[0.5, 0.5], [0.5, 0.5]])
    empty_state_returns = simulate_returns(
        model,
        np.ones(120, dtype=int),
        pd.Series([np.nan] * 120),
        [7],
        simulations=3,
        rng=np.random.default_rng(3),
    )
    assert empty_state_returns[7]["p50"] == 0.0


def test_fit_hmm_forecast_meta_and_errors():
    df = _synthetic_ohlcv(rows=220)
    with pytest.raises(RuntimeError, match="too little"):
        fit_hmm_forecast("X", _synthetic_ohlcv(rows=50))

    result = fit_hmm_forecast(
        "BTC",
        df,
        meta={
            "product_id": "BTC-USD",
            "coin": "BTC",
            "open_interest": 1.0,
            "funding": 0.01,
            "max_leverage": 20,
            "day_notional_volume": 1000.0,
        },
        horizons=(7,),
        n_states=2,
        simulations=20,
        seed=1,
    )
    assert result["product_id"] == "BTC-USD"
    assert result["coin"] == "BTC"
    assert result["open_interest"] == 1.0

    dash_result = fit_hmm_forecast(
        "ETH-USD",
        df,
        horizons=(7,),
        n_states=2,
        simulations=20,
        seed=1,
    )
    assert dash_result["product_id"] == "ETH-USD"

    coin_result = fit_hmm_forecast(
        "BTC",
        df,
        horizons=(7,),
        n_states=2,
        simulations=20,
        seed=1,
    )
    assert coin_result["coin"] == "BTC"


def test_evaluate_filters_volume_and_drawdown():
    df = _synthetic_ohlcv(rows=220)
    ok, reason = evaluate_filters(df, {"quote_volume_24h": 1.0}, {"min_quote_volume_24h": 10.0})
    assert ok is False
    assert "24h" in reason

    ok, reason = evaluate_filters(df, {}, {"min_avg_quote_volume_30d": 1e12})
    assert ok is False
    assert "30d" in reason

    ok, reason = evaluate_filters(df, {}, {"max_drawdown_60d": 0.0})
    assert ok is False
    assert "drawdown" in reason


def test_run_hmm_screen_nan_and_exception(monkeypatch):
    df = _synthetic_ohlcv(rows=220)

    def fake_fit(*args, **kwargs):
        return {"symbol": "NAN", "score": float("nan"), "forecasts": {}}

    monkeypatch.setattr("fast_trade.ml.hmm_screen.fit_hmm_forecast", fake_fit)
    payload = run_hmm_screen({}, [{"symbol": "NAN", "df": df, "meta": {}}])
    assert payload["skipped"][0]["reason"] == "model produced NaN score"

    def boom(*args, **kwargs):
        raise RuntimeError("fit failed")

    monkeypatch.setattr("fast_trade.ml.hmm_screen.fit_hmm_forecast", boom)
    payload = run_hmm_screen({}, [{"symbol": "ERR", "df": df, "meta": {}}])
    assert payload["skipped"][0]["reason"] == "fit failed"


def test_format_markdown_warnings_and_skipped():
    payload = {
        "generated_at": "2024-01-01",
        "settings": {"horizons": [7, 30]},
        "results": [{"symbol": "A", "price": 1.0, "quote_volume_24h": 1.0, "avg_quote_volume_30d": 1.0,
                     "max_drawdown_60d": -0.1, "score": 1.0, "warnings": ["warn"], "forecasts": {
                         "7": {"p25": 0.01, "p50": 0.02, "p75": 0.03},
                         "30": {"p25": 0.01, "p50": 0.02, "p75": 0.03},
                     }}],
        "skipped": [{"symbol": "B", "reason": "bad"}],
    }
    md = format_markdown(payload, title="Warn Screen")
    assert "Model Warnings" in md
    assert "Skipped" in md
