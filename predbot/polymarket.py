"""Read-only client for Polymarket's public APIs. No account or API key needed."""
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
_UA = {"User-Agent": "predbot-paper/1.0"}


def _get(url: str, timeout: float = 20.0):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _json_list(value):
    if isinstance(value, list):
        return value
    if not value:
        return []
    return json.loads(value)


def _f(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


@dataclass
class Outcome:
    name: str
    token_id: str
    bid: float
    ask: float
    day_change: float
    week_change: float
    last_price: float


@dataclass
class Market:
    id: str
    question: str
    slug: str
    event_id: str
    end_date: datetime | None
    liquidity: float
    volume_24h: float
    active: bool
    closed: bool
    accepting_orders: bool
    outcomes: list[Outcome] = field(default_factory=list)
    final_prices: list[float] = field(default_factory=list)
    token_ids: list[str] = field(default_factory=list)
    fee_rate: float = 0.0       # taker fee: fee per share = rate * (p * (1 - p)) ** exponent
    fee_exponent: float = 1.0
    category: str = "other"     # sports / crypto / politics / other, from the fee schedule
    start_date: datetime | None = None
    closed_time: datetime | None = None

    @property
    def url(self) -> str:
        return f"https://polymarket.com/market/{self.slug}"

    def outcome(self, token_id: str) -> Outcome | None:
        return next((o for o in self.outcomes if o.token_id == token_id), None)

    def taker_fee(self, price: float) -> float:
        """Fee per share for a taker trade at this price (Polymarket charges none at settlement)."""
        return self.fee_rate * (price * (1 - price)) ** self.fee_exponent

    def settlement_price(self, token_id: str) -> float | None:
        """1.0 or 0.0 once the market has resolved, otherwise None."""
        if not self.closed or token_id not in self.token_ids:
            return None
        price = self.final_prices[self.token_ids.index(token_id)]
        if price >= 0.99:
            return 1.0
        if price <= 0.01:
            return 0.0
        return None


def category_of(fee_type: str | None) -> str:
    fee_type = fee_type or ""
    for name in ("sports", "crypto", "politics"):
        if fee_type.startswith(name):
            return name
    return "other"


def parse_market(raw: dict) -> Market | None:
    """Turn a Gamma API market into a Market. Only binary markets are supported."""
    names = _json_list(raw.get("outcomes"))
    tokens = _json_list(raw.get("clobTokenIds"))
    prices = [_f(p) for p in _json_list(raw.get("outcomePrices"))]
    if len(names) != 2 or len(tokens) != 2 or len(prices) != 2:
        return None

    # Gamma's bestBid/bestAsk/price changes refer to the first outcome; the
    # second outcome's book is the mirror image (buying No = selling Yes).
    bid0 = _f(raw.get("bestBid"), None)
    ask0 = _f(raw.get("bestAsk"), None)
    if bid0 is None or ask0 is None or not (0 <= bid0 <= ask0 <= 1):
        bid0 = ask0 = None
    day = _f(raw.get("oneDayPriceChange"))
    week = _f(raw.get("oneWeekPriceChange"))
    last0 = _f(raw.get("lastTradePrice"), prices[0])

    outcomes = []
    if bid0 is not None:
        outcomes = [
            Outcome(names[0], str(tokens[0]), bid0, ask0, day, week, last0),
            Outcome(names[1], str(tokens[1]), round(1 - ask0, 4), round(1 - bid0, 4),
                    -day, -week, round(1 - last0, 4)),
        ]

    events = raw.get("events") or [{}]
    schedule = raw.get("feeSchedule") or {}
    fee_rate = _f(schedule.get("rate")) if raw.get("feesEnabled") else 0.0
    return Market(
        id=str(raw.get("id")),
        question=raw.get("question", ""),
        slug=raw.get("slug", ""),
        event_id=str(events[0].get("id", raw.get("id"))),
        end_date=_parse_time(raw.get("endDate")),
        liquidity=_f(raw.get("liquidityNum", raw.get("liquidity"))),
        volume_24h=_f(raw.get("volume24hr")),
        active=bool(raw.get("active")),
        closed=bool(raw.get("closed")),
        accepting_orders=bool(raw.get("acceptingOrders", True)),
        outcomes=outcomes,
        final_prices=prices,
        token_ids=[str(t) for t in tokens],
        fee_rate=fee_rate,
        fee_exponent=_f(schedule.get("exponent"), 1.0),
        category=category_of(raw.get("feeType")),
        start_date=_parse_time(raw.get("startDate")),
        closed_time=_parse_time(raw.get("closedTime")),
    )


class PolymarketClient:
    def __init__(self):
        self._tags: dict[str, list[str]] = {}

    def list_open_markets(self, pages: int = 10, page_size: int = 100) -> list[Market]:
        markets = []
        for page in range(pages):
            q = urllib.parse.urlencode({
                "active": "true", "closed": "false", "archived": "false",
                "limit": page_size, "offset": page * page_size,
                "order": "volume24hr", "ascending": "false",
            })
            batch = _get(f"{GAMMA}/markets?{q}")
            markets += [m for m in map(parse_market, batch) if m]
            if len(batch) < page_size:  # the API caps pages at 100 rows
                break
        return markets

    def get_market(self, market_id: str) -> Market | None:
        return parse_market(_get(f"{GAMMA}/markets/{urllib.parse.quote(market_id)}"))

    def price_history(self, token_id: str, start_ts: int | None = None,
                      end_ts: int | None = None) -> list[tuple[int, float]]:
        """Hourly (timestamp, price) points for a token, oldest first."""
        q = {"market": token_id, "fidelity": 60}
        if start_ts and end_ts:
            q.update(startTs=start_ts, endTs=end_ts)
        else:
            q["interval"] = "max"
        data = _get(f"{CLOB}/prices-history?{urllib.parse.urlencode(q)}")
        return [(int(h["t"]), _f(h["p"])) for h in data.get("history", [])]

    def list_resolved_markets(self, pages: int = 40, page_size: int = 100,
                              min_volume: float = 20_000, order: str = "closedTime") -> list[dict]:
        """Raw Gamma rows for recently resolved markets, newest first (training data)."""
        rows = []
        for page in range(pages):
            q = urllib.parse.urlencode({
                "closed": "true", "limit": page_size, "offset": page * page_size,
                "order": order, "ascending": "false", "volume_num_min": min_volume,
            })
            try:
                batch = _get(f"{GAMMA}/markets?{q}")
            except urllib.error.HTTPError as e:
                if e.code == 422:   # the API stops paging after a few thousand rows
                    break
                raise
            rows += batch
            if len(batch) < page_size:
                break
        return rows

    def get_event_tags(self, event_id: str) -> list[str]:
        """Topic tags for an event (e.g. 'senate-midterms'), used to spot related bets."""
        if event_id not in self._tags:
            event = _get(f"{GAMMA}/events/{urllib.parse.quote(event_id)}")
            self._tags[event_id] = [t["slug"] for t in event.get("tags") or [] if t.get("slug")]
        return self._tags[event_id]

    def get_asks(self, token_id: str) -> list[tuple[float, float]]:
        """Ask levels for a token as (price, size), cheapest first."""
        book = _get(f"{CLOB}/book?token_id={urllib.parse.quote(token_id)}")
        levels = [(_f(a["price"]), _f(a["size"])) for a in book.get("asks", [])]
        return sorted(levels)
