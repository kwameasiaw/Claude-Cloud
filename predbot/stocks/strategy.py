"""Buy short, sharp dips in stocks that are in a long-term uptrend.

Entry: price above its 200-day average (uptrend) and the 2-day RSI below 10 (an
unusually sharp two-day drop). Exit: when the price climbs back above its 5-day
average (the dip has recovered), at the stop-loss, or after 10 trading days.
Strategies like this tend to win often with small gains, so the break-even win
rate on the dashboard matters as much as the win rate itself.
"""
from dataclasses import dataclass

UNIVERSE = {
    "SPY": ("S&P 500 index fund", "index"), "QQQ": ("Nasdaq-100 index fund", "index"),
    "AAPL": ("Apple", "tech"), "MSFT": ("Microsoft", "tech"), "NVDA": ("Nvidia", "tech"),
    "GOOGL": ("Alphabet", "tech"), "META": ("Meta", "tech"), "AVGO": ("Broadcom", "tech"),
    "ORCL": ("Oracle", "tech"), "CRM": ("Salesforce", "tech"), "AMD": ("AMD", "tech"),
    "AMZN": ("Amazon", "consumer"), "TSLA": ("Tesla", "consumer"), "COST": ("Costco", "consumer"),
    "WMT": ("Walmart", "consumer"), "HD": ("Home Depot", "consumer"), "NFLX": ("Netflix", "consumer"),
    "JPM": ("JPMorgan Chase", "finance"), "V": ("Visa", "finance"), "MA": ("Mastercard", "finance"),
    "BAC": ("Bank of America", "finance"), "BRK.B": ("Berkshire Hathaway", "finance"),
    "LLY": ("Eli Lilly", "health"), "UNH": ("UnitedHealth", "health"), "JNJ": ("Johnson & Johnson", "health"),
    "ABBV": ("AbbVie", "health"), "XOM": ("ExxonMobil", "energy"), "PG": ("Procter & Gamble", "staples"),
}

RSI_ENTRY = 10.0
MAX_HOLD_DAYS = 14          # calendar days, about 10 trading days
ATR_STOP_MULT = 2.5
MIN_STOP, MAX_STOP = 0.03, 0.08


def sma(closes: list[float], n: int) -> float | None:
    return sum(closes[-n:]) / n if len(closes) >= n else None


def rsi(closes: list[float], n: int = 2) -> float | None:
    if len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for a, b in zip(closes[-n - 1:], closes[-n:]):
        gains += max(0.0, b - a)
        losses += max(0.0, a - b)
    if losses == 0:
        return 100.0
    return 100 - 100 / (1 + gains / losses)


def atr(bars: list[dict], n: int = 14) -> float | None:
    if len(bars) < n + 1:
        return None
    trs = [max(b["h"] - b["l"], abs(b["h"] - a["c"]), abs(b["l"] - a["c"]))
           for a, b in zip(bars[-n - 1:], bars[-n:])]
    return sum(trs) / n


@dataclass
class StockSignal:
    symbol: str
    name: str
    sector: str
    price: float
    stop: float
    rsi2: float
    sma200: float
    reasons: list[str]


def evaluate(symbol: str, bars: list[dict], ask: float) -> StockSignal | None:
    closes = [b["c"] for b in bars]
    s200, r2, a14 = sma(closes, 200), rsi(closes), atr(bars)
    if s200 is None or r2 is None or a14 is None:
        return None
    if closes[-1] <= s200 or r2 >= RSI_ENTRY:
        return None
    if ask > closes[-1] * 1.01:          # already bounced today; the dip is gone
        return None
    dist = min(MAX_STOP, max(MIN_STOP, ATR_STOP_MULT * a14 / ask))
    name, sector = UNIVERSE.get(symbol, (symbol, "other"))
    return StockSignal(symbol, name, sector, ask, round(ask * (1 - dist), 2), r2, s200, [
        f"{(closes[-1] / s200 - 1) * 100:+.1f}% above its 200-day average (uptrend)",
        f"2-day RSI {r2:.1f} (sharp dip)", f"stop {dist*100:.1f}% below"])


def exit_reason(bars: list[dict], bid: float, stop: float, held_days: float) -> str | None:
    if bid <= stop:
        return "stop-loss"
    s5 = sma([b["c"] for b in bars], 5)
    if s5 and bid > s5:
        return "take-profit"
    if held_days >= MAX_HOLD_DAYS:
        return "time-exit"
    return None
