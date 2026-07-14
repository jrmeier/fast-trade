"""Cover LIVE page/view when live_history is non-empty (cli.py:1558, 1776)."""

import threading

import fast_trade.cli as cli_mod


class _AutoStopEvent(threading.Event):
    def __init__(self, *a, **k):
        super().__init__()
        self._checks = 0

    def is_set(self):
        self._checks += 1
        return self._checks > 1 or super().is_set()


class _NoopThread:
    def __init__(self, target=None, daemon=None):
        self._target = target

    def start(self):
        return None

    def is_alive(self):
        return False

    def join(self, timeout=None):
        return None


def test_live_page_and_view_with_history(archive_env, backtest_run, monkeypatch):
    monkeypatch.setattr(cli_mod.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(cli_mod.sys.stdout, "isatty", lambda: True)
    run_id, _, _ = backtest_run

    histories = []
    real_deque = cli_mod.deque

    def tracking_deque(*a, **k):
        d = real_deque(*a, **k)
        histories.append(d)
        return d

    monkeypatch.setattr(cli_mod, "deque", tracking_deque)
    monkeypatch.setattr(cli_mod.threading, "Event", _AutoStopEvent)
    monkeypatch.setattr(cli_mod.threading, "Thread", _NoopThread)
    monkeypatch.setattr(cli_mod.time, "sleep", lambda *_: None)

    seeded = {"done": False}
    cmds = iter(["LIVE", "LIVE VIEW", "Q"])

    class Sess:
        def prompt(self, *a, **k):
            if histories and not seeded["done"]:
                for d in histories:
                    d.append("2024-01-01 | ENTER | close=1.0")
                seeded["done"] = True
            try:
                return next(cmds)
            except StopIteration:
                return "Q"

    monkeypatch.setattr(cli_mod, "PromptSession", lambda **kw: Sess())
    cli_mod.terminal_cmd(run_id=run_id, index=None, page_size=5)
