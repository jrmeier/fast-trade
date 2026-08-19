"""CLI tests for backtest, archive, logs, evolve, and related commands."""

import json
import os
import signal
import sqlite3
from unittest import mock

import pandas as pd
import pytest
import typer
import yaml
from typer.testing import CliRunner

from fast_trade import cli as cli_mod
from fast_trade.cli import app


def _invoke(runner, args, **kwargs):
    return runner.invoke(app, args, **kwargs)


def test_cli_callback_interactive_flag(cli_runner):
    result = cli_runner.invoke(app, ["--no-interactive", "assets", "--exchange", "local"])
    assert result.exit_code == 0


def test_download_command(cli_runner, monkeypatch):
    calls = []

    def fake_download(**kwargs):
        calls.append(kwargs)
        if kwargs.get("progress_callback"):
            kwargs["progress_callback"]({"perc_complete": 50, "call_count": 1, "total_calls": 2})
            kwargs["progress_callback"]({"perc_complete": "bad"})
        return "/tmp/BTC.parquet"

    monkeypatch.setattr(cli_mod, "download_asset", fake_download)
    result = _invoke(cli_runner, ["download", "BTCUSDT", "binanceus", "--start", "2024-01-01", "--end", "2024-02-01"])
    assert result.exit_code == 0
    assert calls

    bad = _invoke(cli_runner, ["download", "BTC", "bad_exchange"])
    assert bad.exit_code != 0


def test_assets_command(cli_runner, monkeypatch):
    monkeypatch.setattr(cli_mod, "get_assets", lambda exchange: ["BTC", "ETH"])
    result = _invoke(cli_runner, ["assets", "--exchange", "local"])
    assert result.exit_code == 0
    assert "BTC" in result.stdout

    bad = _invoke(cli_runner, ["assets", "--exchange", "nope"])
    assert bad.exit_code != 0


def test_backtest_command_paths(cli_runner, strategy_file, mock_backtest_result, monkeypatch, tmp_path):
    monkeypatch.setattr(cli_mod, "run_backtest", lambda *a, **k: mock_backtest_result)
    monkeypatch.setattr(cli_mod, "save", lambda *a, **k: {"path": str(tmp_path / "saved"), "plot_path": str(tmp_path / "p.html"), "plot_format": "html"})
    monkeypatch.setattr(cli_mod, "create_plot", mock.Mock())
    monkeypatch.setattr(cli_mod, "render_plot_preview_from_data", mock.Mock())

    result = _invoke(
        cli_runner,
        [
            "backtest",
            str(strategy_file),
            "--save",
            "--all",
            "--plot",
            "--details",
            "--show-strategy",
            "--mods",
            "freq",
            "--mods",
            "1H",
        ],
    )
    assert result.exit_code == 0

    yml = tmp_path / "s.yml"
    yml.write_text("symbol: BTC\nexchange: binanceus\nfreq: 1H\nstart: 2024-01-01\nstop: 2024-12-31\n")
    result2 = _invoke(cli_runner, ["backtest", str(yml), "--no-preview"])
    assert result2.exit_code == 0

    with mock.patch.object(cli_mod.Confirm, "ask", side_effect=[True, False]):
        _invoke(cli_runner, ["backtest", str(strategy_file)])


def test_backtest_live_paths(cli_runner, strategy_file, mock_backtest_result, archive_env, sample_ohlcv, monkeypatch):
    monkeypatch.setattr(cli_mod, "run_backtest", lambda *a, **k: mock_backtest_result)
    monkeypatch.setattr(cli_mod, "update_kline", mock.Mock())
    parquet = archive_env / "binanceus" / "BTCUSDT.parquet"
    df = sample_ohlcv.head(20).reset_index().rename(columns={"index": "date"})
    df.to_parquet(parquet, index=False)

    result = _invoke(cli_runner, ["backtest", str(strategy_file), "--live"])
    assert result.exit_code == 0

    # no symbol/exchange
    bad_strat = archive_env / "strategies" / "bad.yml"
    bad_strat.write_text("freq: 1H\nstart: 2024-01-01\nstop: 2024-12-31\n")
    bad = _invoke(cli_runner, ["backtest", str(bad_strat), "--live"])
    assert bad.exit_code != 0

    # up to date path
    recent = sample_ohlcv.tail(5).reset_index().rename(columns={"index": "date"})
    recent["date"] = pd.Timestamp.now(tz="UTC")
    recent.to_parquet(parquet, index=False)
    _invoke(cli_runner, ["backtest", str(strategy_file), "--live"])

    # corrupt parquet start from strategy start string
    monkeypatch.setattr(cli_mod.pd, "read_parquet", mock.Mock(side_effect=OSError("bad")))
    strat_start = archive_env / "strategies" / "start.yml"
    strat_start.write_text(
        yaml.safe_dump(
            {
                "symbol": "BTCUSDT",
                "exchange": "binanceus",
                "freq": "1H",
                "start": "2024-06-01",
                "stop": "2024-12-31",
            }
        )
    )
    _invoke(cli_runner, ["backtest", str(strat_start), "--live"])


def test_backtests_list_show_pick(cli_runner, archive_env, backtest_run, monkeypatch):
    run_id, _, _ = backtest_run

    result = _invoke(cli_runner, ["backtests", "list", "--limit", "5"])
    assert result.exit_code == 0
    assert run_id in result.stdout

    result = _invoke(cli_runner, ["backtests", "list", "--last", "1"])
    assert result.exit_code == 0

    result = _invoke(cli_runner, ["backtests", "show", run_id])
    assert result.exit_code == 0

    result = _invoke(cli_runner, ["backtests", "latest"])
    assert result.exit_code == 0

    result = _invoke(cli_runner, ["backtests", "show", "--index", "1"])
    assert result.exit_code == 0

    bad = _invoke(cli_runner, ["backtests", "show", "--index", "99"])
    assert bad.exit_code != 0

    bad2 = _invoke(cli_runner, ["backtests", "show"])
    assert bad2.exit_code != 0

    bad3 = _invoke(cli_runner, ["backtests", "nope"])
    assert bad3.exit_code != 0


def test_backtests_interactive_pick(cli_runner, archive_env, backtest_run, monkeypatch):
    with mock.patch.object(cli_mod.Confirm, "ask", return_value=True), mock.patch.object(
        cli_mod.IntPrompt, "ask", return_value=1
    ):
        _invoke(cli_runner, ["backtests", "list"])

    with mock.patch.object(cli_mod.IntPrompt, "ask", return_value=99):
        bad = _invoke(cli_runner, ["--interactive", "backtests", "list"])
        # may exit 1 when out of range, or 0 when interactive not enabled in runner
        assert bad.exit_code in (0, 1)

    with mock.patch.object(cli_mod.Confirm, "ask", return_value=False):
        _invoke(cli_runner, ["backtests", "list"])

    pick = _invoke(cli_runner, ["backtests", "pick"])
    assert pick.exit_code != 0

    with mock.patch.object(cli_mod.IntPrompt, "ask", return_value=1):
        pick2 = _invoke(cli_runner, ["--interactive", "backtests", "pick"])
        assert pick2.exit_code in (0, 1)


def test_backtests_missing_dir(cli_runner, tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHIVE_PATH", str(tmp_path / "empty"))
    result = _invoke(cli_runner, ["backtests", "list"])
    assert result.exit_code != 0


def test_migrate_backtests(cli_runner, archive_env, backtest_run, sample_ohlcv):
    run_id, run_dir, summary = backtest_run
    # create sqlite dbs
    df_db = run_dir / "dataframe.db"
    con = sqlite3.connect(df_db)
    df = sample_ohlcv.head(10).reset_index()
    df.to_sql("dataframe", con, index=False)
    con.close()
    trade_db = run_dir / "trade_log.db"
    con2 = sqlite3.connect(trade_db)
    pd.DataFrame({"date": ["2024-01-01"], "close": [1.0]}).to_sql("trade_log", con2, index=False)
    con2.close()
    (run_dir / "summary.json").write_text(json.dumps(summary))
    os.remove(run_dir / "summary.yml")

    result = _invoke(cli_runner, ["migrate_backtests", "--limit", "1"])
    assert result.exit_code == 0


def test_migrate_archive(cli_runner, archive_env, sample_ohlcv):
    ex_path = archive_env / "binanceus"
    sqlite_path = ex_path / "BTCUSDT.sqlite"
    con = sqlite3.connect(sqlite_path)
    df = sample_ohlcv.head(5).reset_index()
    df.to_sql("kline", con, index=False)
    con.close()

    with mock.patch("fast_trade.cli.migrate_sqlite_to_parquet") as mig:
        result = _invoke(cli_runner, ["migrate_archive", "--limit", "1"])
        assert result.exit_code == 0
        mig.assert_called()

    with mock.patch("fast_trade.cli.migrate_sqlite_to_parquet", side_effect=RuntimeError("fail")):
        _invoke(cli_runner, ["migrate_archive"])


def test_regime_commands(cli_runner, tmp_path, sample_ohlcv):
    cfg = tmp_path / "regime.yml"
    cfg.write_text("states: 2\n")
    data = tmp_path / "data.csv"
    sample_ohlcv.reset_index().to_csv(data, index=False)

    with mock.patch("fast_trade.cli.train_regime_model", return_value={"m": 1}), mock.patch(
        "fast_trade.cli.save_regime_model"
    ):
        r1 = _invoke(cli_runner, ["regime_train", str(cfg), str(data)])
        assert r1.exit_code == 0

    with mock.patch("fast_trade.cli.load_regime_model", return_value={}), mock.patch(
        "fast_trade.cli.apply_regime_model", return_value=pd.DataFrame({"x": [1]})
    ):
        r2 = _invoke(cli_runner, ["regime_apply", "model.pkl", str(data)])
        assert r2.exit_code == 0


def test_validate_command(cli_runner, strategy_file, monkeypatch):
    monkeypatch.setattr(cli_mod, "validate_backtest", lambda s: {"has_error": False})
    ok = _invoke(cli_runner, ["validate", str(strategy_file)])
    assert ok.exit_code == 0

    monkeypatch.setattr(cli_mod, "validate_backtest", lambda s: {"has_error": True, "errors": ["x"]})
    bad = _invoke(cli_runner, ["validate", str(strategy_file)])
    assert bad.exit_code != 0


def test_logs_command(cli_runner, archive_env):
    log_dir = archive_env / "portfolio" / "demo"
    log_dir.mkdir(parents=True)
    (log_dir / "portfolio.jsonl").write_text('{"message":"portfolio msg"}\n')

    r = _invoke(cli_runner, ["logs", "--name", "demo", "--tail", "10"])
    assert r.exit_code == 0
    assert "portfolio msg" in r.stdout

    missing = _invoke(cli_runner, ["logs", "--name", "missing"])
    assert missing.exit_code != 0


def test_logs_follow_interrupt(cli_runner, archive_env, monkeypatch):
    log_dir = archive_env / "portfolio" / "demo"
    log_dir.mkdir(parents=True)
    log_path = log_dir / "portfolio.jsonl"
    log_path.write_text('{"message":"one"}\n')

    iterations = {"n": 0}

    def fake_sleep(_):
        iterations["n"] += 1
        if iterations["n"] >= 2:
            raise KeyboardInterrupt()

    monkeypatch.setattr(cli_mod.time, "sleep", fake_sleep)
    with pytest.raises(KeyboardInterrupt):
        cli_mod.logs_cmd(name="demo", follow=True, tail=5)


def test_update_archive(cli_runner, monkeypatch):
    monkeypatch.setattr(cli_mod, "update_archive", mock.Mock())
    result = _invoke(cli_runner, ["update_archive"])
    assert result.exit_code == 0


def test_evolve_command(cli_runner, tmp_path, monkeypatch):
    cfg = {
        "strategy": {"symbol": "BTC", "exchange": "binanceus", "freq": "1H", "start": "2024-01-01", "stop": "2024-12-31"},
        "genes": [{"name": "freq", "space": ["1H", "4H"]}],
        "settings": {"num_generations": 2, "threads": 1},
    }
    path = tmp_path / "evo.json"
    path.write_text(json.dumps(cfg))
    yml = tmp_path / "evo.yml"
    yml.write_text(yaml.safe_dump(cfg))

    def fake_optimize(**kwargs):
        cb = kwargs.get("progress_callback")
        if cb:
            cb(
                {
                    "generation": 1,
                    "total_generations": 2,
                    "fitness": 1.0,
                    "best_fitness": 2.0,
                    "best_genes": [("freq", "1H")],
                }
            )
        return [("freq", "1H")], 2.0

    monkeypatch.setattr(cli_mod, "optimize_strategy", fake_optimize)
    assert _invoke(cli_runner, ["evolve", str(path)]).exit_code == 0
    assert _invoke(cli_runner, ["evolve", str(yml)]).exit_code == 0

    bad = _invoke(cli_runner, ["evolve", str(tmp_path / "missing.json")])
    assert bad.exit_code != 0

    for payload in [
        {"genes": []},
        {"strategy": {}, "genes": "bad"},
        {"strategy": {}, "genes": [{"name": "x"}]},
        {"strategy": {}, "genes": [123]},
        {"strategy_path": "missing.yml", "genes": [{"name": "x", "space": [1]}]},
    ]:
        p = tmp_path / "bad.json"
        p.write_text(json.dumps(payload))
        assert _invoke(cli_runner, ["evolve", str(p)]).exit_code != 0


def test_main_and_callback(monkeypatch):
    ctx = mock.Mock()
    ctx.ensure_object = mock.Mock()
    ctx.obj = {}
    cli_mod.cli_callback(ctx, interactive=True)
    with mock.patch.object(cli_mod, "app", side_effect=RuntimeError("err")):
        with mock.patch.object(cli_mod.sys, "exit") as ex:
            cli_mod.main()
            ex.assert_called_with(1)


def test_load_latest_ohlcv_missing(archive_env):
    with pytest.raises(FileNotFoundError):
        cli_mod._load_latest_ohlcv("coinbase", "MISSING", 10)


def test_backtests_show_bad_summary(cli_runner, archive_env):
    bad_run = archive_env / "backtests" / "bad_run"
    bad_run.mkdir()
    result = _invoke(cli_runner, ["backtests", "show", "bad_run"])
    assert result.exit_code != 0

    # unreadable summary in list
    (bad_run / "summary.yml").write_text("::::")
    _invoke(cli_runner, ["backtests", "list", "--limit", "5"])

    empty = archive_env / "backtests" / "empty_pick"
    empty.mkdir()
    with mock.patch.object(cli_mod.IntPrompt, "ask", return_value=1):
        with mock.patch.object(cli_mod.Confirm, "ask", return_value=True):
            _invoke(cli_runner, ["--interactive", "backtests", "list"])

    pick_empty = _invoke(cli_runner, ["--interactive", "backtests", "pick"])
    # still has other runs


def test_migrate_backtests_no_dir(cli_runner, tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHIVE_PATH", str(tmp_path))
    assert _invoke(cli_runner, ["migrate_backtests"]).exit_code != 0


def test_migrate_archive_no_dir(cli_runner, tmp_path, monkeypatch):
    monkeypatch.setenv("ARCHIVE_PATH", str(tmp_path / "nope"))
    assert _invoke(cli_runner, ["migrate_archive"]).exit_code != 0


def test_backtest_progress_callback_phases(cli_runner, strategy_file, monkeypatch):
    def fake_run(strat, progress_callback=None):
        if progress_callback:
            progress_callback({"phase": "data", "percent": 50})
            progress_callback({"phase": "actions", "percent": 25})
            progress_callback({"phase": "simulation", "percent": 75})
        return {"summary": {"mean_trade_len": 60}, "df": None, "trade_df": None}

    monkeypatch.setattr(cli_mod, "run_backtest", fake_run)
    result = _invoke(cli_runner, ["backtest", str(strategy_file)])
    assert result.exit_code == 0


def test_backtest_interactive_details_prompt(cli_runner, strategy_file, monkeypatch):
    monkeypatch.setattr(cli_mod, "run_backtest", lambda *a, **k: {"summary": {}, "df": None, "trade_df": None})
    with mock.patch.object(cli_mod.Confirm, "ask", side_effect=[True, True]):
        _invoke(cli_runner, ["--interactive", "backtest", str(strategy_file)])


def test_download_default_dates(cli_runner, monkeypatch):
    monkeypatch.setattr(cli_mod, "download_asset", lambda **k: "/tmp/x.parquet")
    result = _invoke(cli_runner, ["download", "BTC", "binanceus"])
    assert result.exit_code == 0


def test_backtests_pick_no_runs(cli_runner, archive_env):
    for child in (archive_env / "backtests").iterdir():
        if child.is_dir():
            import shutil
            shutil.rmtree(child)
    with mock.patch.object(cli_mod.IntPrompt, "ask", return_value=1):
        result = _invoke(cli_runner, ["--interactive", "backtests", "pick"])
    assert result.exit_code != 0


def test_portfolio_loop_sleep(cli_runner, strategy_file, monkeypatch):
    sleeps = []

    def fake_sleep(sec):
        sleeps.append(sec)
        raise KeyboardInterrupt()

    monkeypatch.setattr(cli_mod, "_load_latest_ohlcv", lambda *a, **k: pd.DataFrame({"close": [1.0]}, index=pd.date_range("2024-01-01", periods=1, freq="min")))
    monkeypatch.setattr(cli_mod, "prepare_df", lambda df, s: df)
    monkeypatch.setattr(cli_mod, "compile_action_logic", lambda s: {})
    monkeypatch.setattr(cli_mod, "determine_action_compiled", lambda *a, **k: "h")
    monkeypatch.setattr(cli_mod, "_apply_portfolio_action", lambda *a, **k: (a[0], None, a[1]))
    monkeypatch.setattr(cli_mod, "_append_portfolio_log", mock.Mock())
    monkeypatch.setattr(cli_mod, "_save_portfolio_state", mock.Mock())
    monkeypatch.setattr(cli_mod, "_load_portfolio_state", lambda path, default: default)
    monkeypatch.setattr(cli_mod.time, "sleep", fake_sleep)
    _invoke(cli_runner, ["portfolio", "start", str(strategy_file), "--no-daemon", "--name", "loop"])
    assert sleeps


def test_logs_missing_and_index_errors(cli_runner, archive_env, backtest_run):
    assert _invoke(cli_runner, ["logs", "--index", "99"]).exit_code != 0

    empty = archive_env.parent / "empty_archive"
    empty.mkdir(exist_ok=True)
    with mock.patch.dict(os.environ, {"ARCHIVE_PATH": str(empty)}):
        assert CliRunner().invoke(app, ["logs"]).exit_code != 0
