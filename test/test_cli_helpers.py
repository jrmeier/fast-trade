"""Tests for fast_trade.cli_helpers."""

import json
import os
from unittest import mock

import pandas as pd
import pytest

from fast_trade.cli_helpers import (
    MissingStrategyFile,
    _load_json_or_yaml,
    _parse_simple_yaml,
    create_plot,
    open_strat_file,
    render_plot_preview,
    render_plot_preview_from_data,
    save,
)


def test_parse_simple_yaml_quotes_and_list_items():
    text = 'name: "quoted"\nitems:\n  - plain\n  - key: val\n  - "x"\n'
    parsed = _parse_simple_yaml(text)
    assert parsed["name"] == "quoted"
    assert "items" in parsed

    empty_series_text = "key: []\n"
    assert _parse_simple_yaml(empty_series_text)["key"] == []

    bracket = "tags: [\"a,b\", 'c']"
    parsed2 = _parse_simple_yaml(bracket)
    assert isinstance(parsed2.get("tags"), list)

    single = "label: 'single'\n"
    assert _parse_simple_yaml(single)["label"] == "single"


def test_render_plot_preview_from_data_empty_series(capsys):
    df = pd.DataFrame({"close": []}, index=pd.DatetimeIndex([]))
    render_plot_preview_from_data(df, None)


def test_parse_simple_yaml_nested_lists_and_scalars():
    text = """
name: Test
items:
  - a: 1
  - b: two
flags: [true, false, null]
count: 3
ratio: 1.5
"""
    parsed = _parse_simple_yaml(text)
    assert parsed["name"] == "Test"
    assert parsed["count"] == 3
    assert parsed["ratio"] == 1.5
    assert parsed["flags"] == [True, False, None]
    assert isinstance(parsed["items"], list)


def test_save_without_pyyaml(tmp_path, monkeypatch, mock_backtest_result):
    monkeypatch.setattr("fast_trade.cli_helpers.ARCHIVE_PATH", str(tmp_path))
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("no yaml")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    with mock.patch("fast_trade.cli_helpers.create_plot") as cp:
        fig = mock.Mock()
        cp.return_value = fig
        result = save(mock_backtest_result, save_all=False)
    assert os.path.exists(result["path"])


def test_load_json_or_yaml_json_and_yaml(tmp_path):
    json_path = tmp_path / "s.json"
    json_path.write_text(json.dumps({"a": 1}))
    assert _load_json_or_yaml(str(json_path)) == {"a": 1}

    yaml_path = tmp_path / "s.yml"
    yaml_path.write_text("key: value\nnested:\n  x: 1\n")
    loaded = _load_json_or_yaml(str(yaml_path))
    assert loaded["key"] == "value"
    assert loaded["nested"]["x"] == 1


def test_load_json_or_yaml_fallback_without_pyyaml(tmp_path, monkeypatch):
    yaml_path = tmp_path / "s.yml"
    yaml_path.write_text("name: fallback\nvalue: 42\n")

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("no yaml")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    loaded = _load_json_or_yaml(str(yaml_path))
    assert loaded["name"] == "fallback"


def test_open_strat_file_local_and_url(tmp_path):
    path = tmp_path / "strat.json"
    path.write_text(json.dumps({"symbol": "BTC"}))
    assert open_strat_file(str(path))["symbol"] == "BTC"

    with pytest.raises(MissingStrategyFile):
        open_strat_file(str(tmp_path / "missing.json"))

    resp = mock.Mock(status_code=200)
    resp.json.return_value = {"symbol": "ETH"}
    with mock.patch("fast_trade.cli_helpers.requests.get", return_value=resp):
        assert open_strat_file("https://example.com/strat.json")["symbol"] == "ETH"

    bad = mock.Mock(status_code=404)
    with mock.patch("fast_trade.cli_helpers.requests.get", return_value=bad):
        with pytest.raises(MissingStrategyFile):
            open_strat_file("https://example.com/bad.json")


def test_create_plot_with_and_without_trades(capsys):
    df = pd.DataFrame({"close": [1.0, 2.0, 3.0]}, index=pd.date_range("2024-01-01", periods=3, freq="h"))
    trade_df = pd.DataFrame(
        {"close": [2.0], "in_trade": [True]},
        index=pd.date_range("2024-01-02", periods=1, freq="h"),
    )
    fig = create_plot(df, trade_df, show=False)
    assert fig is not None

    empty_trades = pd.DataFrame()
    fig2 = create_plot(df, empty_trades, show=False)
    assert fig2 is not None

    fig3 = create_plot(df, trade_df, show=False)
    with mock.patch("plotly.graph_objects.Figure.show") as show:
        create_plot(df, trade_df, show=True)
        show.assert_called()


def test_render_plot_preview_from_data_paths(capsys, sample_ohlcv):
    render_plot_preview_from_data(None, None)
    render_plot_preview_from_data(pd.DataFrame(), None)
    no_close = pd.DataFrame({"open": [1.0]}, index=pd.date_range("2024-01-01", periods=1, freq="h"))
    render_plot_preview_from_data(no_close, None)

    df = sample_ohlcv.head(30)
    indices = df.index[::10][:3]
    trade_df = pd.DataFrame(
        {"close": df.loc[indices, "close"].values, "in_trade": [True] * len(indices)},
        index=indices,
    )
    render_plot_preview_from_data(df, trade_df, width=20, height=6)
    out = capsys.readouterr().out
    assert out

    bad_trade = pd.DataFrame({"close": [1.0], "in_trade": [True]}, index=["not-in-df"])
    render_plot_preview_from_data(df, bad_trade)


def test_save_creates_backtest_dir(tmp_path, monkeypatch, mock_backtest_result):
    monkeypatch.setattr("fast_trade.cli_helpers.ARCHIVE_PATH", str(tmp_path))
    with mock.patch("fast_trade.cli_helpers.create_plot") as cp:
        fig = mock.Mock()
        fig.write_image.side_effect = RuntimeError("no kaleido")

        def _write_html(path, *args, **kwargs):
            with open(path, "w") as fh:
                fh.write("<html></html>")

        fig.write_html.side_effect = _write_html
        cp.return_value = fig
        result = save(mock_backtest_result, save_all=True)
    assert os.path.isdir(result["path"])
    assert result["plot_format"] == "html"
    assert os.path.exists(result["plot_path"])


def test_save_png_path(tmp_path, monkeypatch, mock_backtest_result):
    monkeypatch.setattr("fast_trade.cli_helpers.ARCHIVE_PATH", str(tmp_path / "save2"))
    with mock.patch("fast_trade.cli_helpers.create_plot") as cp:
        fig = mock.Mock()
        cp.return_value = fig
        result = save(mock_backtest_result, save_all=False)
    assert result["plot_format"] == "png"


def test_render_plot_preview_no_pil(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(__import__("sys").modules, "PIL", None)
    render_plot_preview(str(tmp_path / "missing.png"))


def test_render_plot_preview_with_pil(tmp_path, capsys):
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("PIL not installed")
    img_path = tmp_path / "plot.png"
    Image.new("L", (10, 10), color=128).save(img_path)
    render_plot_preview(str(img_path), width=10)
    # output may be empty for very small images; ensure no exception

    with mock.patch("PIL.Image.open", side_effect=OSError("bad")):
        render_plot_preview(str(img_path))
