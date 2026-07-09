import json
import os
from typing import Any, Dict, Mapping, Optional
import urllib.error
import urllib.parse
import urllib.request


Params = Mapping[str, Any]


class FXMacroDataClient:
    """REST client for macro, FX, COT, commodity, and session data."""

    DEFAULT_BASE_URL = "https://fxmacrodata.com/api/v1/"

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

    def request(
        self,
        path: str,
        params: Optional[Params] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        query = dict(params or {})
        if self.api_key:
            query["api_key"] = self.api_key
        url = urllib.parse.urljoin(self.base_url, path.lstrip("/"))
        if query:
            url = url + "?" + urllib.parse.urlencode(query)

        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                payload = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"FXMacroData request failed with HTTP {exc.code}: {body}"
            ) from exc
        return json.loads(payload)

    def data_catalogue(self, currency: str) -> Dict[str, Any]:
        return self.request(f"data_catalogue/{currency.lower()}")

    def announcements(
        self, currency: str, indicator: str, **params: Any
    ) -> Dict[str, Any]:
        return self.request(
            f"announcements/{currency.lower()}/{indicator}",
            params,
        )

    def latest_announcements(self, currency: str, **params: Any) -> Dict[str, Any]:
        return self.request(f"announcements/{currency.lower()}/latest", params)

    def calendar(self, currency: str, **params: Any) -> Dict[str, Any]:
        return self.request(f"calendar/{currency.lower()}", params)

    def predictions(
        self, currency: str, indicator: str, **params: Any
    ) -> Dict[str, Any]:
        return self.request(f"predictions/{currency.lower()}/{indicator}", params)

    def forex(self, base: str, quote: str = "usd", **params: Any) -> Dict[str, Any]:
        return self.request(f"forex/{base.lower()}/{quote.lower()}", params)

    def cot(self, currency: str, **params: Any) -> Dict[str, Any]:
        return self.request(f"cot/{currency.lower()}", params)

    def commodity(self, indicator: str, **params: Any) -> Dict[str, Any]:
        return self.request(f"commodities/{indicator}", params)

    def commodities_latest(self, **params: Any) -> Dict[str, Any]:
        return self.request("commodities/latest", params)

    def rate_differentials(
        self, base: str, quote: str = "usd", **params: Any
    ) -> Dict[str, Any]:
        return self.request(
            f"rate_differentials/{base.lower()}/{quote.lower()}",
            params,
        )

    def forward_differentials(
        self, base: str, quote: str = "usd", **params: Any
    ) -> Dict[str, Any]:
        return self.request(
            f"forward_differentials/{base.lower()}/{quote.lower()}",
            params,
        )

    def market_sessions(self, **params: Any) -> Dict[str, Any]:
        return self.request("market_sessions", params)

    def risk_sentiment(self, **params: Any) -> Dict[str, Any]:
        return self.request("risk_sentiment", params)

    def news(self, currency: str, **params: Any) -> Dict[str, Any]:
        return self.request(f"news/{currency.lower()}", params)

    def press_releases(self, currency: str, **params: Any) -> Dict[str, Any]:
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
    return {
        "base_catalogue": client.data_catalogue(base),
        "quote_catalogue": client.data_catalogue(quote),
        "base_calendar": client.calendar(base, limit=limit),
        "quote_calendar": client.calendar(quote, limit=limit),
        "base_announcements": client.announcements(base, indicator, limit=limit),
        "quote_announcements": client.announcements(quote, indicator, limit=limit),
        "forex": client.forex(base, quote, limit=limit),
    }
