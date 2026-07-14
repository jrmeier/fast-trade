import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, Mapping, Optional
import urllib.error
import urllib.parse
import urllib.request


Params = Mapping[str, Any]


class FXMacroDataClient:
    """REST client for macro, FX, COT, commodity, and session data."""

    DEFAULT_BASE_URL = "https://api.fxmacrodata.com/v1/"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 30,
    ) -> None:
        self.api_key = (
            api_key
            or os.getenv("FXMACRODATA_API_KEY")
            or os.getenv("FXMD_API_KEY")
            or ""
        )
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout

    def require_api_key(self, reason: str = "") -> None:
        if self.api_key:
            return
        detail = f" ({reason})" if reason else ""
        raise RuntimeError(
            "FXMacroData API key required. Set FXMACRODATA_API_KEY or FXMD_API_KEY, "
            f"or pass api_key=... when creating FXMacroDataClient.{detail}"
        )

    def _maybe_require_currency_key(self, currency: str) -> None:
        if currency.lower() != "usd":
            self.require_api_key(f"currency={currency.lower()}")

    def request(
        self,
        path: str,
        params: Optional[Params] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        query = dict(params or {})
        url = urllib.parse.urljoin(self.base_url, path.lstrip("/"))
        if query:
            url = url + "?" + urllib.parse.urlencode(query)

        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                payload = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"FXMacroData request failed with HTTP {exc.code}: {body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"FXMacroData request failed for {url}: {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise RuntimeError(
                f"FXMacroData request timed out for {url}"
            ) from exc

        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"FXMacroData response was not valid JSON for {url}: {exc.msg}"
            ) from exc

    def data_catalogue(self, currency: str) -> Dict[str, Any]:
        self._maybe_require_currency_key(currency)
        return self.request(f"data_catalogue/{currency.lower()}")

    def announcements(
        self, currency: str, indicator: str, **params: Any
    ) -> Dict[str, Any]:
        self._maybe_require_currency_key(currency)
        return self.request(
            f"announcements/{currency.lower()}/{indicator}",
            params,
        )

    def latest_announcements(self, currency: str, **params: Any) -> Dict[str, Any]:
        self._maybe_require_currency_key(currency)
        return self.request(f"announcements/{currency.lower()}/latest", params)

    def calendar(self, currency: str, **params: Any) -> Dict[str, Any]:
        self._maybe_require_currency_key(currency)
        return self.request(f"calendar/{currency.lower()}", params)

    def predictions(
        self, currency: str, indicator: str, **params: Any
    ) -> Dict[str, Any]:
        self._maybe_require_currency_key(currency)
        return self.request(f"predictions/{currency.lower()}/{indicator}", params)

    def forex(self, base: str, quote: str = "usd", **params: Any) -> Dict[str, Any]:
        self._maybe_require_currency_key(base)
        self._maybe_require_currency_key(quote)
        return self.request(f"forex/{base.lower()}/{quote.lower()}", params)

    def cot(self, currency: str, **params: Any) -> Dict[str, Any]:
        self._maybe_require_currency_key(currency)
        return self.request(f"cot/{currency.lower()}", params)

    def commodity(self, indicator: str, **params: Any) -> Dict[str, Any]:
        return self.request(f"commodities/{indicator}", params)

    def commodities_latest(self, **params: Any) -> Dict[str, Any]:
        return self.request("commodities/latest", params)

    def rate_differentials(
        self, base: str, quote: str = "usd", **params: Any
    ) -> Dict[str, Any]:
        self._maybe_require_currency_key(base)
        self._maybe_require_currency_key(quote)
        return self.request(
            f"rate_differentials/{base.lower()}/{quote.lower()}",
            params,
        )

    def forward_differentials(
        self, base: str, quote: str = "usd", **params: Any
    ) -> Dict[str, Any]:
        self._maybe_require_currency_key(base)
        self._maybe_require_currency_key(quote)
        return self.request(
            f"forward_differentials/{base.lower()}/{quote.lower()}",
            params,
        )

    def market_sessions(self, **params: Any) -> Dict[str, Any]:
        return self.request("market_sessions", params)

    def risk_sentiment(self, **params: Any) -> Dict[str, Any]:
        return self.request("risk_sentiment", params)

    def news(self, currency: str, **params: Any) -> Dict[str, Any]:
        self._maybe_require_currency_key(currency)
        return self.request(f"news/{currency.lower()}", params)

    def press_releases(self, currency: str, **params: Any) -> Dict[str, Any]:
        self._maybe_require_currency_key(currency)
        return self.request(f"press-releases/{currency.lower()}", params)


def build_macro_context(
    base: str,
    quote: str = "usd",
    indicator: str = "policy_rate",
    limit: int = 10,
    client: Optional[FXMacroDataClient] = None,
) -> Dict[str, Any]:
    client = client or FXMacroDataClient()
    base = base.lower()
    quote = quote.lower()
    jobs: Dict[str, Callable[[], Any]] = {
        "base_catalogue": lambda: client.data_catalogue(base),
        "quote_catalogue": lambda: client.data_catalogue(quote),
        "base_calendar": lambda: client.calendar(base, indicator=indicator),
        "quote_calendar": lambda: client.calendar(quote, indicator=indicator),
        "base_announcements": lambda: client.announcements(
            base, indicator, limit=limit
        ),
        "quote_announcements": lambda: client.announcements(
            quote, indicator, limit=limit
        ),
        "forex": lambda: client.forex(base, quote, limit=limit),
    }

    context: Dict[str, Any] = {}
    errors: Dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {pool.submit(fn): key for key, fn in jobs.items()}
        for future in as_completed(futures):
            key = futures[future]
            try:
                context[key] = future.result()
            except Exception as exc:
                message = str(exc)
                errors[key] = message
                context[key] = {"error": message}

    if errors:
        context["errors"] = errors
    return context
