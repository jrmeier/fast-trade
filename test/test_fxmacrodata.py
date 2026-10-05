import io
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock
from urllib.error import HTTPError, URLError

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

    with mock.patch("fast_trade.fxmacrodata._urlopen", side_effect=fake_urlopen):
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

    monkeypatch.delenv("FXMACRODATA_API_KEY", raising=False)
    monkeypatch.setenv("FXMD_API_KEY", "fxmd-key")
    assert FXMacroDataClient().api_key == "fxmd-key"


def test_require_api_key_includes_reason():
    client = FXMacroDataClient(api_key="")
    with pytest.raises(RuntimeError, match="currency=eur"):
        client.require_api_key("currency=eur")


def test_request_wraps_timeout_errors():
    with mock.patch(
        "fast_trade.fxmacrodata._urlopen",
        side_effect=TimeoutError("timed out"),
    ):
        with pytest.raises(RuntimeError, match="timed out"):
            FXMacroDataClient(api_key="k").data_catalogue("USD")


def test_request_wraps_http_errors():
    error = HTTPError("https://example.test", 401, "Unauthorized", {}, io.BytesIO(b"invalid key"))

    with mock.patch("fast_trade.fxmacrodata._urlopen", side_effect=error):
        with pytest.raises(RuntimeError, match="HTTP 401: invalid key"):
            FXMacroDataClient().data_catalogue("USD")


def test_request_wraps_url_errors():
    with mock.patch(
        "fast_trade.fxmacrodata._urlopen",
        side_effect=URLError("timed out"),
    ):
        with pytest.raises(RuntimeError, match="timed out"):
            FXMacroDataClient().data_catalogue("USD")


def test_request_wraps_invalid_json():
    with mock.patch(
        "fast_trade.fxmacrodata._urlopen",
        return_value=FakeResponse(b"not-json"),
    ):
        with pytest.raises(RuntimeError, match="not valid JSON"):
            FXMacroDataClient().data_catalogue("USD")


def test_non_usd_requests_fail_fast_without_api_key(monkeypatch):
    monkeypatch.delenv("FXMACRODATA_API_KEY", raising=False)
    monkeypatch.delenv("FXMD_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="API key required"):
        FXMacroDataClient().calendar("EUR")


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
    assert "errors" not in context


def test_build_macro_context_returns_partial_success_on_section_errors():
    class StubClient:
        def data_catalogue(self, currency):
            if currency == "eur":
                raise RuntimeError("catalogue down")
            return {"currency": currency}

        def calendar(self, currency, **params):
            return {"currency": currency, "params": params}

        def announcements(self, currency, indicator, **params):
            return {"currency": currency}

        def forex(self, base, quote, **params):
            return {"pair": f"{base}/{quote}"}

    context = build_macro_context("EUR", "USD", client=StubClient())

    assert context["base_catalogue"] == {"error": "catalogue down"}
    assert context["quote_catalogue"] == {"currency": "usd"}
    assert context["errors"]["base_catalogue"] == "catalogue down"


@pytest.mark.parametrize(
    "method,args,expected_path",
    [
        ("announcements", ("USD", "cpi"), "announcements/usd/cpi"),
        ("latest_announcements", ("USD",), "announcements/usd/latest"),
        ("predictions", ("USD", "cpi"), "predictions/usd/cpi"),
        ("forex", ("EUR", "USD"), "forex/eur/usd"),
        ("cot", ("USD",), "cot/usd"),
        ("commodity", ("gold",), "commodities/gold"),
        ("commodities_latest", tuple(), "commodities/latest"),
        ("rate_differentials", ("EUR", "USD"), "rate_differentials/eur/usd"),
        ("forward_differentials", ("EUR", "USD"), "forward_differentials/eur/usd"),
        ("market_sessions", tuple(), "market_sessions"),
        ("risk_sentiment", tuple(), "risk_sentiment"),
        ("news", ("USD",), "news/usd"),
        ("press_releases", ("USD",), "press-releases/usd"),
    ],
)
def test_endpoint_methods_build_expected_paths(method, args, expected_path):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        return FakeResponse(b"{}")

    with mock.patch("fast_trade.fxmacrodata._urlopen", side_effect=fake_urlopen):
        getattr(FXMacroDataClient(api_key="k"), method)(*args)

    assert expected_path in captured["url"]


def test_request_does_not_follow_redirects(monkeypatch):
    for name in ("http_proxy", "HTTP_PROXY", "all_proxy", "ALL_PROXY"):
        monkeypatch.delenv(name, raising=False)
    paths = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            paths.append(self.path)
            if self.path.startswith("/v1/"):
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/target")
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = FXMacroDataClient(api_key="secret-key", base_url=f"http://127.0.0.1:{server.server_port}/v1/")
        with pytest.raises(RuntimeError, match="HTTP 302") as excinfo:
            client.data_catalogue("USD")
    finally:
        server.shutdown()
        server.server_close()

    assert paths == ["/v1/data_catalogue/usd"]
    assert "secret-key" not in str(excinfo.value)


@pytest.mark.parametrize("api_key", ["secret\nkey", "secret key", "secret\x00key"])
def test_request_rejects_bad_api_key_without_echoing_it(api_key):
    with mock.patch("fast_trade.fxmacrodata._urlopen") as fake_urlopen:
        with pytest.raises(RuntimeError, match="invalid characters") as excinfo:
            FXMacroDataClient(api_key=api_key).data_catalogue("USD")

    fake_urlopen.assert_not_called()
    assert "secret" not in str(excinfo.value)


def test_constructor_strips_api_key():
    assert FXMacroDataClient(api_key=" test-key\n").api_key == "test-key"


@pytest.mark.parametrize(
    "body,message",
    [
        (b'{"detail": "Invalid API key"}', "Invalid API key"),
        (b'["not", "an", "object"]', "not a JSON object"),
    ],
)
def test_request_rejects_error_bodies_returned_with_200(body, message):
    with mock.patch("fast_trade.fxmacrodata._urlopen", return_value=FakeResponse(body)):
        with pytest.raises(RuntimeError, match=message):
            FXMacroDataClient().data_catalogue("USD")
