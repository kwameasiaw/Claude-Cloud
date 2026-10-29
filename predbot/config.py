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

    # --- Scan agent: flag and skip anything odd ---------------------------------
    flag_day_move: float = 0.10           # a 10c+ swing in 24h is "weird"; skip until it settles
    flag_spread: float = 0.04             # spreads this wide suggest a broken or thin book

    # --- Research agents ------------------------------------------------------
    research_max_items: int = 12          # headlines/posts per source per market
    research_workers: int = 8             # parallel fetches
    research_top: int = 12                # research only the most promising candidates

    # --- Prediction agent -----------------------------------------------------
    llm_model: str = "claude-opus-5-5"
    llm_weight: float = 0.25              # how far the LLM may pull the estimate...
    llm_max_shift: float = 0.05           # ...and never more than 5c either way
    min_confidence: float = 0.55          # only fire above this confidence score
    model_path: str = "models/calibration.json"
    model_meta_path: str = "models/calibration_meta.json"
    examples_path: str = "models/training_examples.json"
    calibration_path: str = "models/calibration_table.json"

    # --- Risk agent -----------------------------------------------------------
    kelly_fraction: float = 0.25          # quarter-Kelly: a quarter of the "optimal" bet
    max_drawdown_halt: float = 0.25       # stop new bets if the pot is 25% below its start
    daily_loss_halt: float = 0.10         # pause new bets for the day after a 10% drop

    # --- Postmortems ----------------------------------------------------------
    lesson_min_repeats: int = 3           # a lesson only changes behaviour once seen 3 times
    postmortem_path: str = "postmortems.jsonl"
    lessons_path: str = "lessons.json"

    # --- Stocks pot (separate £100, simulated against Alpaca's live quotes) ---
    stocks_state_path: str = "stocks_state.json"
    stocks_journal_path: str = "stocks_journal.csv"

    # --- Files ----------------------------------------------------------------
    state_path: str = "paper_state.json"
    journal_path: str = "trade_journal.csv"
    dashboard_path: str = "dashboard.html"
