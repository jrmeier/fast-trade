import json
from pathlib import Path

from fast_trade.ml.evolution.reporter import (
    ConsoleReporter,
    FileReporter,
    CompositeReporter,
)


def test_console_reporter_does_not_raise(capsys):
    r = ConsoleReporter()
    r.report({"x": 1})
    out, err = capsys.readouterr()
    assert "\n" in out


def test_file_reporter_writes(tmp_path):
    r = FileReporter(str(tmp_path), "payload.json")
    payload = {"hello": "world"}
    r.report(payload)
    p = Path(tmp_path) / "payload.json"
    assert p.exists()
    data = json.loads(p.read_text())
    assert data == payload


def test_composite_reporter_all_called(tmp_path, capsys):
    console = ConsoleReporter()
    file_r = FileReporter(str(tmp_path), "payload.json")
    comp = CompositeReporter([console, file_r])
    comp.report({"a": 2})
    # console wrote something
    out, _ = capsys.readouterr()
    assert "\n" in out
    # file written
    assert (Path(tmp_path) / "payload.json").exists()
