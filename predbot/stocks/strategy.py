"""Buy short, sharp dips in stocks that are in a long-term uptrend.

Entry: price above its 200-day average (uptrend) and the 2-day RSI below 10 (an
unusually sharp two-day drop). Exit: when the price climbs back above its 5-day
average (the dip has recovered), at the stop-loss, or after 10 trading days.
Strategies like this tend to win often with small gains, so the break-even win
rate on the dashboard matters as much as the win rate itself.

The crypto pot runs the same rules on the biggest coins, with wider stops because
coins swing about three times as much as large stocks.
"""
from dataclasses import dataclass, field

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

CRYPTO_UNIVERSE = {
    "BTC/USD": ("Bitcoin", "major"), "ETH/USD": ("Ether", "major"),
    "SOL/USD": ("Solana", "altcoin"), "XRP/USD": ("XRP", "altcoin"), "DOGE/USD": ("Dogecoin", "altcoin"),
    "LINK/USD": ("Chainlink", "altcoin"), "AVAX/USD": ("Avalanche", "altcoin"), "LTC/USD": ("Litecoin", "altcoin"),
    "BCH/USD": ("Bitcoin Cash", "altcoin"), "DOT/USD": ("Polkadot", "altcoin"), "UNI/USD": ("Uniswap", "altcoin"),
    "AAVE/USD": ("Aave", "altcoin"),
}


@dataclass(frozen=True)
class Rules:
    universe: dict = field(default_factory=lambda: UNIVERSE)
    rsi_entry: float = 10.0
    max_hold_days: float = 14       # calendar days, about 10 trading days
    atr_stop_mult: float = 2.5
    min_stop: float = 0.03
    max_stop: float = 0.08
    max_spread: float = 0.005       # skip quotes with a bid-ask spread over 0.5%
    decimals: int = 2               # price rounding for stops


STOCK_RULES = Rules()
# Coins trade every day, so 10 calendar days is 10 trading days; stops sit 5-15% away.
CRYPTO_RULES = Rules(universe=CRYPTO_UNIVERSE, max_hold_days=10, min_stop=0.05, max_stop=0.15,
                     max_spread=0.007, decimals=6)


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


def evaluate(symbol: str, bars: list[dict], ask: float, rules: Rules = STOCK_RULES) -> StockSignal | None:
    closes = [b["c"] for b in bars]
    s200, r2, a14 = sma(closes, 200), rsi(closes), atr(bars)
    if s200 is None or r2 is None or a14 is None:
        return None
    if closes[-1] <= s200 or r2 >= rules.rsi_entry:
        return None
    if ask > closes[-1] * 1.01:          # already bounced today; the dip is gone
        return None
    dist = min(rules.max_stop, max(rules.min_stop, rules.atr_stop_mult * a14 / ask))
    name, sector = rules.universe.get(symbol, (symbol, "other"))
    return StockSignal(symbol, name, sector, ask, round(ask * (1 - dist), rules.decimals), r2, s200, [
        f"{(closes[-1] / s200 - 1) * 100:+.1f}% above its 200-day average (uptrend)",
        f"2-day RSI {r2:.1f} (sharp dip)", f"stop {dist*100:.1f}% below"])


def exit_reason(bars: list[dict], bid: float, stop: float, held_days: float,
                rules: Rules = STOCK_RULES) -> str | None:
    if bid <= stop:
        return "stop-loss"
    s5 = sma([b["c"] for b in bars], 5)
    if s5 and bid > s5:
        return "take-profit"
    if held_days >= rules.max_hold_days:
        return "time-exit"
    return None
