"""Alpaca market data (free IEX feed) and market clock. Needs a free paper-trading
account's keys in APCA_API_KEY_ID and APCA_API_SECRET_KEY. No orders are sent:
the stock pot is simulated locally against Alpaca's live quotes, like the Polymarket pot.
"""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

DATA = "https://data.alpaca.markets/v2"
CRYPTO = "https://data.alpaca.markets/v1beta3/crypto/us"
TRADING = "https://paper-api.alpaca.markets/v2"


def configured() -> bool:
    return bool(os.environ.get("APCA_API_KEY_ID") and os.environ.get("APCA_API_SECRET_KEY"))


def _get(url: str):
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": os.environ["APCA_API_KEY_ID"],
        "APCA-API-SECRET-KEY": os.environ["APCA_API_SECRET_KEY"],
        "User-Agent": "predbot-paper/1.0",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


class AlpacaClient:
    def clock(self) -> dict:
        return _get(f"{TRADING}/clock")

    def daily_bars(self, symbols: list[str], days: int = 330) -> dict[str, list[dict]]:
        """Split-adjusted daily bars per symbol, oldest first: {t, o, h, l, c, v}."""
        start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        out: dict[str, list[dict]] = {s: [] for s in symbols}
        token = None
        while True:
            q = {"symbols": ",".join(symbols), "timeframe": "1Day", "start": start,
                 "limit": 10000, "adjustment": "split", "feed": "iex"}
            if token:
                q["page_token"] = token
            data = _get(f"{DATA}/stocks/bars?{urllib.parse.urlencode(q)}")
            for sym, bars in (data.get("bars") or {}).items():
                out[sym] += bars
            token = data.get("next_page_token")
            if not token:
                return out

    def latest_quotes(self, symbols: list[str]) -> dict[str, tuple[float, float]]:
        """{symbol: (bid, ask)}; symbols without a usable two-sided quote are left out."""
        q = urllib.parse.urlencode({"symbols": ",".join(symbols), "feed": "iex"})
        data = _get(f"{DATA}/stocks/quotes/latest?{q}")
        out = {}
        for sym, quote in (data.get("quotes") or {}).items():
            bid, ask = float(quote.get("bp") or 0), float(quote.get("ap") or 0)
            if 0 < bid <= ask:
                out[sym] = (bid, ask)
        return out


class AlpacaCryptoClient:
    """Same interface as AlpacaClient, for coins quoted in US dollars (e.g. BTC/USD).
    Crypto trades around the clock, so the clock is always open."""

    def clock(self) -> dict:
        return {"is_open": True}

    def daily_bars(self, symbols: list[str], days: int = 330) -> dict[str, list[dict]]:
        start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        out: dict[str, list[dict]] = {s: [] for s in symbols}
        token = None
        while True:
            q = {"symbols": ",".join(symbols), "timeframe": "1Day", "start": start, "limit": 10000}
            if token:
                q["page_token"] = token
            data = _get(f"{CRYPTO}/bars?{urllib.parse.urlencode(q)}")
            for sym, bars in (data.get("bars") or {}).items():
                out[sym] += bars
            token = data.get("next_page_token")
            if not token:
                return out

    def latest_quotes(self, symbols: list[str]) -> dict[str, tuple[float, float]]:
        q = urllib.parse.urlencode({"symbols": ",".join(symbols)})
        data = _get(f"{CRYPTO}/latest/quotes?{q}")
        out = {}
        for sym, quote in (data.get("quotes") or {}).items():
            bid, ask = float(quote.get("bp") or 0), float(quote.get("ap") or 0)
            if 0 < bid <= ask:
                out[sym] = (bid, ask)
        return out
