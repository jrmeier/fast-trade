import json
from typing import Any, Dict, List

import requests

from fast_trade.ml.evolution.utils import sanitize_for_json, atomic_write_json


class Reporter:
    def report(self, payload: Dict[str, Any]) -> None:
        pass


class ConsoleReporter(Reporter):
    def report(self, payload: Dict[str, Any]) -> None:
        payload_str = json.dumps(payload, indent=2)
        print("-" * 50)
        print(payload_str)
        print("-" * 50)


class FileReporter(Reporter):
    def __init__(self, directory: str, filename: str = "payload.json"):
        self.directory = directory
        self.filename = filename

    def report(self, payload: Dict[str, Any]) -> None:
        sanitized = sanitize_for_json(payload)
        full_path = f"{self.directory}/{self.filename}"
        atomic_write_json(full_path, sanitized)


class WebhookReporter(Reporter):
    def __init__(self, url: str, timeout_seconds: int = 10):
        self.url = url
        self.timeout_seconds = timeout_seconds

    def report(self, payload: Dict[str, Any]) -> None:
        try:
            sanitized = sanitize_for_json(payload)
            requests.post(self.url, json=sanitized, timeout=self.timeout_seconds)
        except Exception as e:
            print(f"Error sending payload to api: {e}")


class CompositeReporter(Reporter):
    def __init__(self, reporters: List[Reporter]):
        self.reporters = reporters

    def report(self, payload: Dict[str, Any]) -> None:
        for reporter in self.reporters:
            try:
                reporter.report(payload)
            except Exception as e:
                print(f"Reporter error: {e}")
