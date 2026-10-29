"""All tunable settings live here. Every number is a deliberate choice; see README."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # --- Bankroll -----------------------------------------------------------
    starting_bankroll: float = 100.0      # paper GBP (Polymarket quotes USD; we treat units as £)
    stake_fraction: float = 0.10          # each trade risks 10% of current equity
    min_stake: float = 2.0                # don't bother with dust trades
    max_open_positions: int = 5           # keeps >=50% of the pot in cash at all times
    max_per_theme: int = 2                # e.g. at most 2 bets on the US midterms at once

    # --- Market filters (only trade liquid, honest-priced markets) -----------
    min_liquidity: float = 10_000.0       # USD resting on the book
    min_volume_24h: float = 5_000.0       # USD traded in the last day
    max_spread: float = 0.02              # 2 cents max between bid and ask
    min_hours_to_close: float = 24.0      # avoid last-minute news gaps
    max_days_to_close: float = 30.0       # avoid locking capital up for months

    # --- Entry ----------------------------------------------------------------
    # Buy the favourite only when it is priced in this band. A contract bought
    # at price p wins about p of the time if the market is fair, so this band
    # is what produces a 60-80% expected win rate.
    min_entry_price: float = 0.60
    max_entry_price: float = 0.82
    max_day_drop: float = 0.03            # skip if the favourite fell >3c today
    max_week_drop: float = 0.05           # ...or >5c this week (falling knife)
    min_edge: float = 0.005               # fair value must beat ask + taker fee by 0.5c
    max_book_slippage: float = 0.01       # stake must fill within 1c of best ask

    # --- Exits ----------------------------------------------------------------
    stop_loss_pct: float = 0.20           # sell if bid falls 20% below entry price
    take_profit_price: float = 0.95       # lock in once the bid reaches 95c
    exit_hours_before_close: float = 0.0  # 0 = hold to resolution if no stop/target hit

    # --- Files ----------------------------------------------------------------
    state_path: str = "paper_state.json"
    journal_path: str = "trade_journal.csv"
    dashboard_path: str = "dashboard.html"
