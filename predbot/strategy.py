"""Shared market rules: basic filters, related-bet caps, order-book fills and exits."""
from datetime import datetime

from .config import Config
from .polymarket import Market


def hours_to_close(market: Market, now: datetime) -> float | None:
    if market.end_date is None:
        return None
    return (market.end_date - now).total_seconds() / 3600


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
