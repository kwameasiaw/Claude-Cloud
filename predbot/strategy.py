"""Decides which markets are worth trading, and when to get out.

The idea: on prediction markets, heavy favourites tend to resolve YES slightly
more often than their price implies, and longshots slightly less (the
"favourite-longshot bias"). So we only buy liquid favourites priced 60-82c
that are not falling, and only when that small bias still beats the spread.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from .config import Config
from .polymarket import Market, Outcome


@dataclass
class Signal:
    market: Market
    outcome: Outcome
    fair_value: float
    edge: float
    reasons: list[str]


def hours_to_close(market: Market, now: datetime) -> float | None:
    if market.end_date is None:
        return None
    return (market.end_date - now).total_seconds() / 3600


def fair_value(o: Outcome) -> float:
    """Price-implied probability nudged for the favourite-longshot bias and trend."""
    mid = (o.bid + o.ask) / 2
    bias = 0.03 * (mid - 0.5) / 0.5            # up to +3c for heavy favourites
    trend = 0.25 * max(0.0, min(o.week_change, 0.08))  # small credit for steady rise
    return min(0.99, mid + bias + trend)


def rejection(market: Market, cfg: Config, now: datetime) -> str | None:
    """Why a market fails the basic filters, or None if it passes."""
    if market.closed or not market.active or not market.accepting_orders:
        return "not open for trading"
    if not market.outcomes:
        return "no live quotes"
    if market.liquidity < cfg.min_liquidity:
        return f"liquidity ${market.liquidity:,.0f} too thin"
    if market.volume_24h < cfg.min_volume_24h:
        return f"24h volume ${market.volume_24h:,.0f} too low"
    spread = market.outcomes[0].ask - market.outcomes[0].bid
    if spread > cfg.max_spread + 1e-9:
        return f"spread {spread:.3f} too wide"
    hrs = hours_to_close(market, now)
    if hrs is None:
        return "no end date"
    if hrs < cfg.min_hours_to_close:
        return "closes too soon"
    if hrs > cfg.max_days_to_close * 24:
        return "closes too far out"
    return None


def evaluate(market: Market, cfg: Config, now: datetime | None = None) -> Signal | None:
    now = now or datetime.now(timezone.utc)
    if rejection(market, cfg, now):
        return None
    fav = max(market.outcomes, key=lambda o: o.ask)
    if not (cfg.min_entry_price <= fav.ask <= cfg.max_entry_price):
        return None
    if fav.day_change < -cfg.max_day_drop or fav.week_change < -cfg.max_week_drop:
        return None
    fv = fair_value(fav)
    fee = market.taker_fee(fav.ask)
    edge = fv - fav.ask - fee
    if edge < cfg.min_edge:
        return None
    reasons = [
        f"favourite '{fav.name}' at {fav.ask:.2f}" + (f" +{fee*100:.1f}c fee" if fee else ""),
        f"fair {fv:.3f} (edge {edge*100:.1f}c after fees)",
        f"24h {fav.day_change*100:+.1f}c, 7d {fav.week_change*100:+.1f}c",
        f"liq ${market.liquidity:,.0f}, vol24h ${market.volume_24h:,.0f}",
        f"closes in {hours_to_close(market, now)/24:.1f}d",
    ]
    return Signal(market, fav, fv, edge, reasons)


def scan(markets: list[Market], cfg: Config, now: datetime | None = None) -> list[Signal]:
    """Best opportunities first, at most one per event (they move together)."""
    signals = [s for s in (evaluate(m, cfg, now) for m in markets) if s]
    signals.sort(key=lambda s: s.edge, reverse=True)
    seen, out = set(), []
    for s in signals:
        if s.market.event_id not in seen:
            seen.add(s.market.event_id)
            out.append(s)
    return out


# Tags too broad to mean two bets are linked.
BROAD_TAGS = {"politics", "elections", "global-elections", "united-states", "world",
              "sports", "crypto", "business", "economy", "culture", "geopolitics",
              "pop-culture", "finance", "tech", "science", "games", "hide-from-new"}


def theme_clash(tags: list[str], open_tags: list[list[str]], cfg: Config) -> str | None:
    """A shared specific tag held by max_per_theme open positions already, if any."""
    for tag in set(tags) - BROAD_TAGS:
        if sum(tag in held for held in open_tags) >= cfg.max_per_theme:
            return tag
    return None


def simulate_fill(asks: list[tuple[float, float]], stake: float) -> tuple[float, float] | None:
    """Walk the ask side of the book; returns (shares, average price) or None if too thin."""
    spent = shares = 0.0
    for price, size in asks:
        if price <= 0:
            continue
        take = min(size, (stake - spent) / price)
        spent += take * price
        shares += take
        if spent >= stake - 1e-9:
            return shares, spent / shares
    return None


def stop_price(entry_price: float, cfg: Config) -> float:
    return round(entry_price * (1 - cfg.stop_loss_pct), 4)


def exit_reason(entry_price: float, bid: float, hrs_left: float | None, cfg: Config) -> str | None:
    if bid <= stop_price(entry_price, cfg):
        return "stop-loss"
    if bid >= cfg.take_profit_price:
        return "take-profit"
    if cfg.exit_hours_before_close and hrs_left is not None and hrs_left <= cfg.exit_hours_before_close:
        return "time-exit"
    return None
