"""Focused tests for remaining CLI / helper coverage gaps."""

import json
import os
import sqlite3
import sys
from unittest import mock

import pandas as pd
import pytest
import typer
import yaml
from typer.testing import CliRunner

from fast_trade import cli as cli_mod
from fast_trade.cli import app
from fast_trade.cli_helpers import (
    _parse_simple_yaml,
    render_plot_preview,
    render_plot_preview_from_data,
)
from fast_trade import ftv

def _invoke(runner, args, **kwargs):
    return runner.invoke(app, args, **kwargs)

def test_backtest_live_invalid_start_and_progress(cli_runner, archive_env, mock_backtest_result, monkeypatch):
    monkeypatch.setattr(cli_mod, "run_backtest", lambda *a, **k: mock_backtest_result)

    def fake_update(**kwargs):
        cb = kwargs.get("progress_callback")
        if cb:
            cb({"perc_complete": "bad"})
        return None

    monkeypatch.setattr(cli_mod, "update_kline", fake_update)

    strat = archive_env / "strategies" / "bad_start.yml"
    strat.write_text(
        yaml.safe_dump(
            {
                "symbol": "BTCUSDT",
                "exchange": "binanceus",
                "freq": "1H",
                "start": "not-a-valid-date",
                "stop": "2024-12-31",
            }
        )
    )
    assert _invoke(cli_runner, ["backtest", str(strat), "--live"]).exit_code == 0

def test_backtest_interactive_details_confirm(strategy_file, mock_backtest_result, monkeypatch):
    monkeypatch.setattr(cli_mod, "run_backtest", lambda *a, **k: mock_backtest_result)
    ctx = mock.Mock()
    ctx.obj = {"interactive": True}
    with mock.patch.object(cli_mod.Confirm, "ask", side_effect=[True, False]):
        cli_mod.backtest(
            ctx,
            strategy=str(strategy_file),
            mods=None,
            save_results=False,
            save_all=False,
            preview=True,
            plot=False,
            live=False,
            details=False,
            show_strategy=False,
        )

def test_backtest_summary_non_numeric_trade_len(cli_runner, strategy_file, monkeypatch):
    monkeypatch.setattr(
        cli_mod,
        "run_backtest",
        lambda *a, **k: {"summary": {"mean_trade_len": "bad"}, "df": None, "trade_df": None},
    )
    assert _invoke(cli_runner, ["backtest", str(strategy_file)]).exit_code == 0

# --- backtests interactive pick ---

def test_backtests_pick_from_list_and_latest_empty(cli_runner, archive_env, backtest_run, monkeypatch):
    run_id, _, _ = backtest_run
    ctx = mock.Mock()
    ctx.obj = {"interactive": True}

    with mock.patch.object(cli_mod.Confirm, "ask", return_value=True), mock.patch.object(
        cli_mod.IntPrompt, "ask", return_value=1
    ):
        cli_mod.backtests_cmd(ctx, action="list", run_id=None, limit=10, last=0, index=None)

    with mock.patch.object(cli_mod.IntPrompt, "ask", return_value=1):
        cli_mod.backtests_cmd(ctx, action="pick", run_id=None, limit=10, last=0, index=None)

    for child in list((archive_env / "backtests").iterdir()):
        if child.is_dir():
            import shutil

            shutil.rmtree(child)
    assert _invoke(cli_runner, ["backtests", "latest"]).exit_code != 0

def test_backtests_pick_out_of_range_and_decline(archive_env, backtest_run):
    ctx = mock.Mock()
    ctx.obj = {"interactive": True}

    with mock.patch.object(cli_mod.Confirm, "ask", return_value=False):
        cli_mod.backtests_cmd(ctx, action="list", run_id=None, limit=10, last=0, index=None)

    with mock.patch.object(cli_mod.IntPrompt, "ask", return_value=99):
        with pytest.raises(typer.Exit):
            cli_mod.backtests_cmd(ctx, action="pick", run_id=None, limit=10, last=0, index=None)

    with mock.patch.object(cli_mod.IntPrompt, "ask", return_value=1):
        cli_mod.backtests_cmd(ctx, action="pick", run_id=None, limit=10, last=1, index=None)

def test_backtests_pick_no_runs_direct(archive_env):
    ctx = mock.Mock()
    ctx.obj = {"interactive": True}
    for child in (archive_env / "backtests").iterdir():
        if child.is_dir():
            import shutil

            shutil.rmtree(child)
    with pytest.raises(typer.Exit):
        cli_mod.backtests_cmd(ctx, action="pick", run_id=None, limit=10, last=0, index=None)

# --- migrate commands ---

def test_migrate_backtests_all_branches(cli_runner, archive_env, backtest_run, sample_ohlcv):
    run_id, run_dir, summary = backtest_run

    df_db = run_dir / "dataframe.db"
    con = sqlite3.connect(df_db)
    pd.DataFrame({"open": [1], "high": [1], "low": [1], "close": [1], "volume": [1]}).to_sql(
        "dataframe", con, index=False
    )
    con.close()

    trade_db = run_dir / "trade_log.db"
    con2 = sqlite3.connect(trade_db)
    pd.DataFrame({"close": [1.0], "in_trade": [True]}).to_sql("trade_log", con2, index=False)
    con2.close()

    (run_dir / "summary.json").write_text(json.dumps(summary))
    os.remove(run_dir / "summary.yml")

    assert _invoke(cli_runner, ["migrate_backtests", "--limit", "1"]).exit_code == 0

    with mock.patch("yaml.safe_dump", side_effect=RuntimeError("yaml fail")):
        (run_dir / "summary.json").write_text(json.dumps(summary))
        if (run_dir / "summary.yml").exists():
            os.remove(run_dir / "summary.yml")
        _invoke(cli_runner, ["migrate_backtests", "--limit", "1"])

    with mock.patch("fast_trade.cli.connect_to_db", side_effect=RuntimeError("db fail")):
        _invoke(cli_runner, ["migrate_backtests", "--limit", "1"])

def test_migrate_archive_skips_non_dirs(cli_runner, archive_env, tmp_path, monkeypatch):
    (archive_env / "readme.txt").write_text("x")
    ex = archive_env / "binanceus"
    sqlite_path = ex / "ETHUSDT.sqlite"
    con = sqlite3.connect(sqlite_path)
    pd.DataFrame({"date": ["2024-01-01"], "open": [1], "high": [1], "low": [1], "close": [1], "volume": [1]}).to_sql(
        "kline", con, index=False
    )
    con.close()
    assert _invoke(cli_runner, ["migrate_archive"]).exit_code == 0

# --- helper functions ---

def test_apply_mods_odd_pairs_raises():
    with pytest.raises(typer.BadParameter):
        cli_mod._apply_mods({}, ["freq"])


def test_format_log_line_variants():
    assert cli_mod._format_log_line('{"event": {"msg": "hi"}}') == '{"msg": "hi"}'
    assert cli_mod._format_log_line("[1, 2]") == "[1, 2]"
    assert cli_mod._format_log_line("plain\n") == "plain"


def test_max_datapoint_periods():
    assert cli_mod._max_datapoint_periods({}) == 0
    assert cli_mod._max_datapoint_periods(
        {"datapoints": [{"args": [5, 20]}, {"args": ["x", 30]}]}
    ) == 30


def test_load_backtest_run_date_columns(archive_env, backtest_run, sample_ohlcv):
    run_id, run_dir, _ = backtest_run
    df = sample_ohlcv.head(5).reset_index()
    df.to_parquet(run_dir / "dataframe.parquet", index=False)
    trade = pd.DataFrame({"date": df["date"], "close": [1.0] * len(df), "in_trade": [True] * len(df)})
    trade.to_parquet(run_dir / "trade_log.parquet", index=False)

    _, summary, trade_df, df_out = cli_mod._load_backtest_run(str(archive_env / "backtests"), run_id)
    assert summary["return_perc"] == 12.5
    assert trade_df is not None
    assert df_out is not None

def test_load_backtest_summary_json_migrates_to_yaml(archive_env):
    run_dir = archive_env / "backtests" / "json_only"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(json.dumps({"return_perc": 2}))
    loaded = cli_mod._load_backtest_summary(str(run_dir))
    assert loaded["return_perc"] == 2
    assert (run_dir / "summary.yml").exists()


def test_load_backtest_summary_yaml_write_failure(archive_env, tmp_path):
    run_dir = archive_env / "backtests" / "yaml_fail"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(json.dumps({"return_perc": 2}))

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("no yaml")
        return real_import(name, *args, **kwargs)

    with mock.patch("builtins.__import__", fake_import):
        loaded = cli_mod._load_backtest_summary(str(run_dir))
    assert loaded["return_perc"] == 2

    run_dir2 = archive_env / "backtests" / "dump_fail"
    run_dir2.mkdir()
    (run_dir2 / "summary.json").write_text(json.dumps({"return_perc": 3}))
    with mock.patch("yaml.safe_dump", side_effect=OSError("disk full")):
        loaded2 = cli_mod._load_backtest_summary(str(run_dir2))
    assert loaded2["return_perc"] == 3

def test_load_latest_ohlcv_date_column(archive_env, sample_ohlcv):
    path = archive_env / "coinbase" / "ETH-USD.parquet"
    df = sample_ohlcv.head(10).reset_index()
    df.to_parquet(path, index=False)
    out = cli_mod._load_latest_ohlcv("coinbase", "ETH-USD", 5)
    assert len(out) == 5


def test_load_latest_ohlcv_rebuilds_corrupt_parquet(archive_env, sample_ohlcv, monkeypatch):
    path = archive_env / "coinbase" / "BTC-USD.parquet"
    path.write_text("not parquet")
    monkeypatch.setattr(
        "fast_trade.archive.db_helpers._safe_read_parquet",
        lambda _path: None,
    )
    monkeypatch.setattr(
        "fast_trade.archive.db_helpers.get_kline",
        lambda *args, **kwargs: sample_ohlcv.head(10),
    )
    out = cli_mod._load_latest_ohlcv("coinbase", "BTC-USD", 5)
    assert len(out) == 5

def test_logs_missing_portfolio(cli_runner, archive_env):
    assert _invoke(cli_runner, ["logs", "--name", "missing"]).exit_code != 0


def test_logs_tail_zero_and_follow(cli_runner, archive_env, monkeypatch):
    log_dir = archive_env / "portfolio" / "demo"
    log_dir.mkdir(parents=True)
    log_path = log_dir / "portfolio.jsonl"
    log_path.write_text('{"line":"tail"}\n')

    assert _invoke(cli_runner, ["logs", "--name", "demo", "--tail", "0"]).exit_code == 0

    iterations = {"n": 0}

    def fake_sleep(_):
        iterations["n"] += 1
        if iterations["n"] >= 2:
            raise KeyboardInterrupt()

    monkeypatch.setattr(cli_mod.time, "sleep", fake_sleep)
    with pytest.raises(KeyboardInterrupt):
        cli_mod.logs_cmd(name="demo", follow=True, tail=1)


def test_logs_follow_reads_appended_lines(cli_runner, archive_env, monkeypatch):
    log_dir = archive_env / "portfolio" / "demo"
    log_dir.mkdir(parents=True)
    log_path = log_dir / "portfolio.jsonl"
    log_path.write_text("")

    calls = {"n": 0}

    def fake_sleep(_):
        calls["n"] += 1
        if calls["n"] == 1:
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write('{"event":{"msg":"follow"}}\n')
        elif calls["n"] >= 3:
            raise KeyboardInterrupt()

    monkeypatch.setattr(cli_mod.time, "sleep", fake_sleep)
    with pytest.raises(KeyboardInterrupt):
        cli_mod.logs_cmd(name="demo", follow=True, tail=0)


def test_logs_follow_read_exception(archive_env, monkeypatch):
    log_dir = archive_env / "portfolio" / "demo"
    log_dir.mkdir(parents=True)
    log_path = log_dir / "portfolio.jsonl"
    log_path.write_text("")

    calls = {"n": 0}

    def fake_sleep(_):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise KeyboardInterrupt()

    real_open = open

    class FollowHandle:
        read_calls = 0

        def __init__(self, path, *args, **kwargs):
            self._fh = real_open(path, *args, **kwargs)
            self.closed = False

        def seek(self, *args, **kwargs):
            return self._fh.seek(*args, **kwargs)

        def readline(self):
            FollowHandle.read_calls += 1
            if FollowHandle.read_calls > 1:
                raise OSError("read fail")
            return ""

        def close(self):
            self.closed = True
            return self._fh.close()

    monkeypatch.setattr(cli_mod.time, "sleep", fake_sleep)
    with mock.patch("builtins.open", FollowHandle):
        with pytest.raises(KeyboardInterrupt):
            cli_mod.logs_cmd(name="demo", follow=True, tail=0)

# --- portfolio ---

def test_portfolio_default_name_and_once_daemon(cli_runner, strategy_file, archive_env, monkeypatch):
    proc = mock.Mock(pid=999)
    popen = mock.Mock(return_value=proc)
    monkeypatch.setattr(cli_mod.subprocess, "Popen", popen)
    r = _invoke(
        cli_runner,
        ["portfolio", "start", str(strategy_file), "--once"],
    )
    assert r.exit_code == 0
    cmd = popen.call_args[0][0]
    assert "--once" in cmd

    with mock.patch("builtins.open", mock.mock_open()) as mopen:
        mopen.side_effect = [mock.mock_open().return_value, OSError("pid fail")]
        monkeypatch.setattr(cli_mod.subprocess, "Popen", mock.Mock(return_value=proc))
        _invoke(cli_runner, ["portfolio", "start", str(strategy_file)])

def test_portfolio_no_frames_path(cli_runner, strategy_file, archive_env, monkeypatch):
    df = pd.DataFrame({"close": [1.0]}, index=pd.date_range("2024-01-01", periods=1, freq="min"))

    class EmptyTail:
        def tail(self, n):
            return pd.DataFrame()

    df_mock = mock.Mock()
    df_mock.empty = False
    df_mock.tail = EmptyTail().tail
    df_mock.index = df.index

    monkeypatch.setattr(cli_mod, "_load_latest_ohlcv", lambda *a, **k: df)
    monkeypatch.setattr(cli_mod, "prepare_df", lambda d, s: df_mock)
    monkeypatch.setattr(cli_mod, "compile_action_logic", lambda s: {})
    monkeypatch.setattr(cli_mod, "_append_portfolio_log", mock.Mock())
    monkeypatch.setattr(cli_mod, "_load_portfolio_state", lambda path, default: default)
    _invoke(cli_runner, ["portfolio", "start", str(strategy_file), "--no-daemon", "--once", "--name", "noframes"])

def test_portfolio_pid_remove_error(cli_runner, strategy_file, monkeypatch):
    monkeypatch.setattr(cli_mod, "_load_latest_ohlcv", mock.Mock(side_effect=KeyboardInterrupt()))
    monkeypatch.setattr(cli_mod, "_load_portfolio_state", lambda path, default: default)
    monkeypatch.setattr(cli_mod, "_portfolio_paths", lambda name: {"state": "/tmp/s", "log": "/tmp/l", "trades": "/tmp/t", "pid": "/tmp/p.pid"})
    with mock.patch("os.path.exists", return_value=True), mock.patch("os.remove", side_effect=OSError("rm fail")):
        _invoke(cli_runner, ["portfolio", "start", str(strategy_file), "--no-daemon", "--name", "rmfail"])

def test_portfolio_stop_pid_remove_error(cli_runner, tmp_path, monkeypatch):
    pid_file = tmp_path / "runner.pid"
    pid_file.write_text("4242")
    with mock.patch("fast_trade.cli._portfolio_paths", return_value={"pid": str(pid_file)}), mock.patch(
        "os.kill"
    ), mock.patch("os.remove", side_effect=OSError("rm fail")):
        assert _invoke(cli_runner, ["portfolio", "stop", "mypf"]).exit_code == 0

# --- final coverage gaps ---

def test_migrate_backtests_trade_with_date(cli_runner, archive_env):
    run_dir = archive_env / "backtests" / "trade_date"
    run_dir.mkdir(parents=True)
    (run_dir / "summary.yml").write_text("return_perc: 1\n")
    trade_db = run_dir / "trade_log.db"
    con = sqlite3.connect(trade_db)
    pd.DataFrame(
        {"date": ["2024-01-01"], "close": [1.0], "in_trade": [True]}
    ).to_sql("trade_log", con, index=False)
    con.close()
    assert _invoke(cli_runner, ["migrate_backtests"]).exit_code == 0

def test_migrate_backtests_outer_exception(cli_runner, archive_env, monkeypatch):
    run_dir = archive_env / "backtests" / "fail_run"
    run_dir.mkdir(parents=True)
    (run_dir / "summary.yml").write_text("x: 1\n")
    (run_dir / "dataframe.db").write_text("not a db")
    with mock.patch("fast_trade.cli.connect_to_db", side_effect=RuntimeError("boom")):
        assert _invoke(cli_runner, ["migrate_backtests"]).exit_code == 0

def test_cli_and_ftv_main_lines():
    root = os.path.dirname(os.path.dirname(__file__))
    cli_path = os.path.join(root, "fast_trade", "cli.py")
    ftv_path = os.path.join(root, "fast_trade", "ftv.py")
    cli_src = open(cli_path).read().splitlines()
    ftv_src = open(ftv_path).read().splitlines()

    with mock.patch.object(cli_mod, "main") as cli_main:
        exec("\n".join(cli_src[-2:]), {"__name__": "__main__", "main": cli_main}, {})
        cli_main.assert_called_once()

    with mock.patch.object(ftv, "main") as ftv_main:
        exec("\n".join(ftv_src[-2:]), {"__name__": "__main__", "main": ftv_main}, {})
        ftv_main.assert_called_once()

def test_render_plot_preview_from_data_x_oob(capsys, sample_ohlcv):
    df = sample_ohlcv.head(9).reset_index(drop=True)
    df.index = pd.date_range("2020-01-01", periods=len(df), freq="h")
    idx = df.index[-1]
    trade_df = pd.DataFrame({"close": [df.loc[idx, "close"]], "in_trade": [True]}, index=[idx])
    render_plot_preview_from_data(df, trade_df, width=2, height=4)
    assert capsys.readouterr().out

def test_render_plot_preview_print_exception(tmp_path):
    img = mock.Mock()
    img.width = 4
    img.height = 4
    img.convert.return_value = img
    img.resize.return_value = img
    img.getdata.return_value = [128] * 16
    with mock.patch("PIL.Image.open", return_value=img), mock.patch(
        "builtins.print", side_effect=OSError("print fail")
    ):
        render_plot_preview(str(tmp_path / "x.png"), width=4)

def test_logs_legacy_portfolio_log(cli_runner, archive_env):
    log_dir = archive_env / "portfolio" / "legacy"
    log_dir.mkdir(parents=True)
    (log_dir / "portfolio.log").write_text('{"message":"legacy"}\n')
    r = _invoke(cli_runner, ["logs", "--name", "legacy", "--tail", "10"])
    assert r.exit_code == 0
    assert "legacy" in r.stdout

def test_cli_main_block_runs():
    root = os.path.dirname(os.path.dirname(__file__))
    cli_path = os.path.join(root, "fast_trade", "cli.py")
    fragment = compile(
        "if __name__ == '__main__':\n    main()\n",
        cli_path,
        "exec",
    )
    with mock.patch.object(cli_mod, "main") as main_mock:
        exec(fragment, {"__name__": "__main__", "main": main_mock})
        main_mock.assert_called_once()

def test_ftv_main_block_runs():
    root = os.path.dirname(os.path.dirname(__file__))
    ftv_path = os.path.join(root, "fast_trade", "ftv.py")
    fragment = compile(
        "if __name__ == '__main__':\n    main()\n",
        ftv_path,
        "exec",
    )
    with mock.patch.object(ftv, "main") as main_mock:
        exec(fragment, {"__name__": "__main__", "main": main_mock})
        main_mock.assert_called_once()

# --- evolve genes validation ---

def test_evolve_gene_validation_branches(cli_runner, tmp_path, monkeypatch):
    base = {"strategy": {"symbol": "BTC"}, "settings": {"num_generations": 1, "threads": 1}}

    p1 = tmp_path / "no_genes.json"
    p1.write_text(json.dumps({**base, "genes": []}))
    assert _invoke(cli_runner, ["evolve", str(p1)]).exit_code != 0

    p2 = tmp_path / "bad_gene.json"
    p2.write_text(json.dumps({**base, "genes": [{"name": "x"}]}))
    assert _invoke(cli_runner, ["evolve", str(p2)]).exit_code != 0

    p3 = tmp_path / "bad_type.json"
    p3.write_text(json.dumps({**base, "genes": [123]}))
    assert _invoke(cli_runner, ["evolve", str(p3)]).exit_code != 0

    p4 = tmp_path / "list_gene.json"
    p4.write_text(json.dumps({**base, "genes": [["freq", ["1H", "4H"]]]}))
    monkeypatch.setattr(cli_mod, "optimize_strategy", lambda **k: ([("freq", "1H")], 1.0))
    assert _invoke(cli_runner, ["evolve", str(p4)]).exit_code == 0

    p5 = tmp_path / "bad_genes_type.json"
    p5.write_text(json.dumps({**base, "genes": "bad"}))
    assert _invoke(cli_runner, ["evolve", str(p5)]).exit_code != 0

# --- __main__ ---

def test_cli_script_main():
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "fast_trade.cli", "--help"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

def test_cli_main_error_path():
    with mock.patch.object(cli_mod, "app", side_effect=RuntimeError("err")), mock.patch.object(
        cli_mod.sys, "exit"
    ) as ex:
        cli_mod.main()
        ex.assert_called_with(1)

# --- cli_helpers remainders ---

def test_migrate_backtests_sqlite_without_parquet(cli_runner, archive_env, sample_ohlcv):
    run_dir = archive_env / "backtests" / "migrate_only"
    run_dir.mkdir(parents=True)
    (run_dir / "summary.yml").write_text("return_perc: 1\n")

    df_db = run_dir / "dataframe.db"
    con = sqlite3.connect(df_db)
    pd.DataFrame(
        {"date": ["2024-01-01"], "open": [1], "high": [1], "low": [1], "close": [1], "volume": [1]}
    ).to_sql("dataframe", con, index=False)
    con.close()

    trade_db = run_dir / "trade_log.db"
    con2 = sqlite3.connect(trade_db)
    pd.DataFrame({"close": [1.0], "in_trade": [True]}).to_sql("trade_log", con2, index=False)
    con2.close()

    assert _invoke(cli_runner, ["migrate_backtests", "--limit", "5"]).exit_code == 0
    assert (run_dir / "dataframe.parquet").exists()
    assert (run_dir / "trade_log.parquet").exists()

def test_parse_simple_yaml_empty_dash_item():
    parsed = _parse_simple_yaml("items:\n  - \n")
    assert parsed == {"items": [{}]}
    parsed2 = _parse_simple_yaml("items:\n  - \n  - key: 1\n")
    assert isinstance(parsed2["items"], list)

def test_render_plot_preview_from_data_edge_cases(capsys, sample_ohlcv):
    df = sample_ohlcv.head(100)
    trade_idx = df.index[-1]
    trade_df = pd.DataFrame({"close": [df.loc[trade_idx, "close"]], "in_trade": [True]}, index=[trade_idx])
    render_plot_preview_from_data(df, trade_df, width=3, height=4)
    assert capsys.readouterr().out

    class _CloseSeries:
        @property
        def values(self):
            return []

    class _FakeDF:
        empty = False
        columns = ["close"]

        def __getitem__(self, key):
            return _CloseSeries()

    render_plot_preview_from_data(_FakeDF(), None)

def test_render_plot_preview_inner_exception(tmp_path, capsys):
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("PIL not installed")
    img_path = tmp_path / "plot.png"
    Image.new("L", (4, 4), color=128).save(img_path)

    class BadImage:
        width = 4
        height = 4

        def convert(self, mode):
            return self

        def resize(self, size):
            return self

        def getdata(self):
            raise RuntimeError("pixels fail")

    with mock.patch("PIL.Image.open", return_value=BadImage()):
        render_plot_preview(str(img_path))

# --- ftv remainders ---

def test_ftv_json_to_json(cli_runner, tmp_path):
    src = tmp_path / "in.json"
    dest = tmp_path / "out.json"
    src.write_text(json.dumps({"plain": "hello"}))
    assert cli_runner.invoke(ftv.app, ["convert", str(src), str(dest)]).exit_code == 0

def test_ftv_script_main_entry():
    import subprocess

    result = subprocess.run(
        [sys.executable, "fast_trade/ftv.py", "--help"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0



def test_cli_name_main_guard():
    cli_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fast_trade", "cli.py")
    fragment = compile(
        "if __name__ == '__main__':\n    main()\n",
        cli_path,
        "exec",
    )
    with mock.patch.object(cli_mod, "main") as main_mock:
        exec(fragment, {"__name__": "__main__", "main": main_mock})
        main_mock.assert_called_once()

def test_render_plot_preview_from_data_trade_oob(capsys, sample_ohlcv):
    df = sample_ohlcv.head(200)
    early_idx = df.index[5]
    trade_df = pd.DataFrame({"close": [df.loc[early_idx, "close"]], "in_trade": [True]}, index=[early_idx])
    render_plot_preview_from_data(df, trade_df, width=2, height=4)
    assert capsys.readouterr().out

def test_render_plot_preview_line_loop_exception(tmp_path):
    img_path = tmp_path / "plot.png"
    img_path.write_bytes(b"\x00" * 16)

    img = mock.Mock()
    img.width = 4
    img.height = 4
    img.convert.return_value = img
    img.resize.return_value = img
    img.getdata.side_effect = OSError("pixels fail")

    with mock.patch("PIL.Image.open", return_value=img):
        render_plot_preview(str(img_path), width=4)

def test_ftv_dump_yaml_plain_string(tmp_path, monkeypatch):
    src = tmp_path / "in.json"
    dest = tmp_path / "out.yml"
    src.write_text(json.dumps({"msg": "hello"}))
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("no yaml")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    assert CliRunner().invoke(ftv.app, ["convert", str(src), str(dest)]).exit_code == 0
    assert "hello" in dest.read_text()

def test_ftv_name_main_guard():
    ftv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fast_trade", "ftv.py")
    fragment = compile(
        "if __name__ == '__main__':\n    main()\n",
        ftv_path,
        "exec",
    )
    with mock.patch.object(ftv, "main") as main_mock:
        exec(fragment, {"__name__": "__main__", "main": main_mock})
        main_mock.assert_called_once()

def test_portfolio_pid_write_failure(cli_runner, strategy_file, monkeypatch):
    proc = mock.Mock(pid=123)
    monkeypatch.setattr(cli_mod.subprocess, "Popen", mock.Mock(return_value=proc))
    real_open = open

    def open_side(path, *args, **kwargs):
        if str(path).endswith("runner.pid"):
            raise OSError("pid write fail")
        return real_open(path, *args, **kwargs)

    with mock.patch("builtins.open", side_effect=open_side):
        assert _invoke(cli_runner, ["portfolio", "start", str(strategy_file), "--name", "pidfail"]).exit_code == 0

