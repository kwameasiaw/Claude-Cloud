"""Step 4: Risk agent. Sizes every bet from the edge and the bankroll, and blocks
anything too big or too risky. The 10%-of-pot rule is a hard ceiling; Kelly sizing
usually asks for less, because the edges are small.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .. import strategy
from ..config import Config


@dataclass
class RiskDecision:
    approved: bool
    stake: float = 0.0
    kelly_fraction: float = 0.0
    reasons: list[str] = field(default_factory=list)


def kelly(p: float, cost: float) -> float:
    """Kelly fraction for a contract that costs `cost` and pays 1 with probability p."""
    if cost >= 1 or p <= cost:
        return 0.0
    return (p - cost) / (1 - cost)


def portfolio_halt(pf, cfg: Config) -> str | None:
    """A reason to stop opening new positions altogether, or None."""
    eq = pf.equity()
    if eq < pf.starting_bankroll * (1 - cfg.max_drawdown_halt):
        return (f"pot is {(1 - eq / pf.starting_bankroll) * 100:.0f}% below its start; "
                "new bets paused until reviewed")
    today = datetime.now(timezone.utc).date().isoformat()
    start_of_day = next((h["equity"] for h in pf.history if h["t"][:10] == today), None)
    if start_of_day and eq < start_of_day * (1 - cfg.daily_loss_halt):
        return f"pot fell {(1 - eq / start_of_day) * 100:.0f}% today; no new bets until tomorrow"
    return None


def check_bet(p: float, cost: float, pf, cfg: Config, tags: list[str]) -> RiskDecision:
    halt = portfolio_halt(pf, cfg)
    if halt:
        return RiskDecision(False, reasons=[halt])
    if len(pf.positions) >= cfg.max_open_positions:
        return RiskDecision(False, reasons=[f"already {cfg.max_open_positions} open bets"])
    clash = strategy.theme_clash(tags, [q.tags for q in pf.positions], cfg)
    if clash:
        return RiskDecision(False, reasons=[f"already {cfg.max_per_theme} bets on '{clash}'"])

    f = kelly(p, cost)
    if f <= 0:
        return RiskDecision(False, reasons=["no edge after fees"])
    equity = pf.equity()
    want = cfg.kelly_fraction * f * equity
    cap = cfg.stake_fraction * equity
    stake = round(min(want, cap, pf.cash), 2)
    reasons = [f"Kelly {f*100:.1f}% of pot -> quarter-Kelly £{want:.2f}",
               f"cap 10% = £{cap:.2f}", f"stake £{stake:.2f}"]
    if stake < cfg.min_stake:
        return RiskDecision(False, stake, f, reasons + [f"below the £{cfg.min_stake:.0f} minimum: edge too thin to be worth it"])
    return RiskDecision(True, stake, f, reasons)


def check_stock(symbol: str, entry: float, stop: float, pf, cfg: Config, sector: str,
                risk_per_trade: float = 0.015) -> RiskDecision:
    """Size a stock trade so hitting the stop loses about 1.5% of the pot, capped at 10%."""
    halt = portfolio_halt(pf, cfg)
    if halt:
        return RiskDecision(False, reasons=[halt])
    if len(pf.positions) >= cfg.max_open_positions:
        return RiskDecision(False, reasons=[f"already {cfg.max_open_positions} open trades"])
    if any(q.market_id == symbol for q in pf.positions):
        return RiskDecision(False, reasons=[f"already holding {symbol}"])
    same = sum(1 for q in pf.positions if sector in q.tags)
    if sector != "index" and same >= cfg.max_per_theme:
        return RiskDecision(False, reasons=[f"already {same} trades in {sector}"])
    if stop >= entry:
        return RiskDecision(False, reasons=["stop is not below entry"])
    equity = pf.equity()
    dist = (entry - stop) / entry
    want = risk_per_trade * equity / dist
    cap = cfg.stake_fraction * equity
    stake = round(min(want, cap, pf.cash), 2)
    reasons = [f"stop {dist*100:.1f}% away", f"risking 1.5% of pot -> £{want:.2f}",
               f"cap 10% = £{cap:.2f}", f"stake £{stake:.2f}"]
    if stake < cfg.min_stake:
        return RiskDecision(False, stake, 0, reasons + ["below minimum trade size"])
    return RiskDecision(True, stake, 0, reasons)
