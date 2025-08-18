import json
import os
import tempfile

from fast_trade.ml.evolution.utils import atomic_write_json


def test_atomic_write_json_creates_file_and_is_valid_json(tmp_path):
    path = tmp_path / "out.json"
    data = {"a": 1, "b": [1, 2, 3]}
    atomic_write_json(str(path), data)
    assert path.exists()
    loaded = json.loads(path.read_text())
    assert loaded == data
