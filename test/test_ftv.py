"""Tests for fast_trade.ftv."""

import json
import os
import sys
from unittest import mock

import pytest
import typer
from typer.testing import CliRunner

from fast_trade import ftv


def test_convert_json_to_yaml(tmp_path, cli_runner):
    src = tmp_path / "in.json"
    dest = tmp_path / "out.yml"
    src.write_text(json.dumps({"name": "test", "value": 1}))
    result = cli_runner.invoke(ftv.app, ["convert", str(src), str(dest)])
    assert result.exit_code == 0
    assert dest.exists()
    assert "name" in dest.read_text()


def test_convert_yaml_to_json(tmp_path, cli_runner):
    src = tmp_path / "in.yml"
    dest = tmp_path / "out.json"
    src.write_text("name: test\nvalue: 1\n")
    result = cli_runner.invoke(ftv.app, ["convert", str(src), str(dest)])
    assert result.exit_code == 0
    assert json.loads(dest.read_text())["name"] == "test"


def test_convert_bad_extension(cli_runner, tmp_path):
    src = tmp_path / "in.txt"
    src.write_text("x")
    result = cli_runner.invoke(ftv.app, ["convert", str(src), str(tmp_path / "out.json")])
    assert result.exit_code != 0


def test_convert_yaml_without_pyyaml(tmp_path, cli_runner, monkeypatch):
    src = tmp_path / "in.yml"
    dest = tmp_path / "out.yml"
    src.write_text("key: val\nlist:\n  - a: 1\n")
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("no yaml")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    result = cli_runner.invoke(ftv.app, ["convert", str(src), str(dest)])
    assert result.exit_code != 0


def test_convert_dump_yaml_fallback(tmp_path, monkeypatch):
    """Exercise dump_yaml branches when PyYAML missing on write."""
    src = tmp_path / "in.json"
    dest = tmp_path / "out.yml"
    src.write_text(
        json.dumps(
            {
                "s": "",
                "n": True,
                "f": False,
                "x": None,
                "d": {"a": 1},
                "l": [1, {"b": 2}],
            }
        )
    )

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("no yaml")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    result = CliRunner().invoke(ftv.app, ["convert", str(src), str(dest)])
    assert result.exit_code == 0
    assert dest.exists()


def test_main_callback_and_main_error():
    ftv.main_callback()
    with mock.patch.object(ftv, "app") as app_mock:
        app_mock.side_effect = RuntimeError("boom")
        with mock.patch.object(sys, "exit") as exit_mock:
            ftv.main()
            exit_mock.assert_called_once_with(1)


def test_ftv_script_main():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "fast_trade/ftv.py", "--help"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_convert_yaml_string_with_colon(tmp_path, cli_runner):
    src = tmp_path / "in.json"
    dest = tmp_path / "out.yml"
    src.write_text(json.dumps({"note": "a:b"}))
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("no yaml")
        return real_import(name, *args, **kwargs)

    import builtins
    orig = builtins.__import__
    builtins.__import__ = fake_import
    try:
        result = cli_runner.invoke(ftv.app, ["convert", str(src), str(dest)])
    finally:
        builtins.__import__ = orig
    assert result.exit_code == 0
    assert ":" in dest.read_text()
