import io
from unittest import mock
from urllib.error import HTTPError

import pytest

from fast_trade.fxmacrodata import FXMacroDataClient, build_macro_context


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


def test_request_uses_canonical_host_query_encoding_and_header_auth():
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["api_key"] = request.get_header("X-api-key")
        captured["timeout"] = timeout
        return FakeResponse(b'{"data": []}')

    with mock.patch("fast_trade.fxmacrodata.urllib.request.urlopen", side_effect=fake_urlopen):
        result = FXMacroDataClient(api_key="test-key", timeout=12).calendar(
            "USD", indicator="policy rate", start_date="2024-01-01"
        )

    assert result == {"data": []}
    assert captured == {
        "url": "https://api.fxmacrodata.com/v1/calendar/usd?indicator=policy+rate&start_date=2024-01-01",
        "api_key": "test-key",
        "timeout": 12,
    }


def test_constructor_reads_api_key_from_environment(monkeypatch):
    monkeypatch.setenv("FXMACRODATA_API_KEY", "environment-key")

    assert FXMacroDataClient().api_key == "environment-key"
    assert FXMacroDataClient(api_key="constructor-key").api_key == "constructor-key"


def test_request_wraps_http_errors():
    error = HTTPError("https://example.test", 401, "Unauthorized", {}, io.BytesIO(b"invalid key"))

    with mock.patch("fast_trade.fxmacrodata.urllib.request.urlopen", side_effect=error):
        with pytest.raises(RuntimeError, match="HTTP 401: invalid key"):
            FXMacroDataClient().data_catalogue("USD")


def test_build_macro_context_filters_calendars_and_does_not_limit_them():
    calls = []

    class StubClient:
        def data_catalogue(self, currency):
            calls.append(("data_catalogue", currency, {}))
            return {"currency": currency}

        def calendar(self, currency, **params):
            calls.append(("calendar", currency, params))
            return {"currency": currency, "params": params}

        def announcements(self, currency, indicator, **params):
            calls.append(("announcements", currency, {"indicator": indicator, **params}))
            return {"currency": currency}

        def forex(self, base, quote, **params):
            calls.append(("forex", f"{base}/{quote}", params))
            return {"pair": f"{base}/{quote}"}

    context = build_macro_context("EUR", "USD", indicator="inflation", limit=5, client=StubClient())

    assert context["base_calendar"]["params"] == {"indicator": "inflation"}
    assert context["quote_calendar"]["params"] == {"indicator": "inflation"}
    assert ("announcements", "eur", {"indicator": "inflation", "limit": 5}) in calls
    assert ("forex", "eur/usd", {"limit": 5}) in calls
