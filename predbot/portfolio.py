"""Paper portfolio: cash, open positions and a closed-trade journal, saved as JSON/CSV."""
import csv
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


@dataclass
class Position:
    market_id: str
    event_id: str
    question: str
    outcome: str
    token_id: str
    shares: float
    entry_price: float
    stake: float
    stop_price: float
    opened_at: str
    url: str = ""
    last_bid: float | None = None


@dataclass
class ClosedTrade:
    market_id: str
    question: str
    outcome: str
    entry_price: float
    exit_price: float
    shares: float
    stake: float
    proceeds: float
    pnl: float
    reason: str
    opened_at: str
    closed_at: str


@dataclass
class Portfolio:
    cash: float
    starting_bankroll: float
    positions: list[Position] = field(default_factory=list)
    closed: list[ClosedTrade] = field(default_factory=list)

    @classmethod
    def load(cls, path: str, starting_bankroll: float) -> "Portfolio":
        if not os.path.exists(path):
            return cls(cash=starting_bankroll, starting_bankroll=starting_bankroll)
        with open(path) as f:
            data = json.load(f)
        return cls(
            cash=data["cash"],
            starting_bankroll=data["starting_bankroll"],
            positions=[Position(**p) for p in data.get("positions", [])],
            closed=[ClosedTrade(**t) for t in data.get("closed", [])],
        )

    def save(self, path: str) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(asdict(self), f, indent=2)
        os.replace(tmp, path)

    def equity(self) -> float:
        """Cash plus open positions marked at their last known bid (what we could sell for)."""
        marked = sum(p.shares * (p.last_bid if p.last_bid is not None else p.entry_price)
                     for p in self.positions)
        return self.cash + marked

    def holds(self, market_id: str, event_id: str) -> bool:
        return any(p.market_id == market_id or p.event_id == event_id for p in self.positions)

    def open(self, pos: Position) -> None:
        self.cash -= pos.stake
        self.positions.append(pos)

    def close(self, pos: Position, exit_price: float, reason: str, journal_path: str | None) -> ClosedTrade:
        proceeds = pos.shares * exit_price
        trade = ClosedTrade(
            market_id=pos.market_id, question=pos.question, outcome=pos.outcome,
            entry_price=pos.entry_price, exit_price=exit_price, shares=pos.shares,
            stake=pos.stake, proceeds=round(proceeds, 4), pnl=round(proceeds - pos.stake, 4),
            reason=reason, opened_at=pos.opened_at,
            closed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        self.cash += proceeds
        self.positions.remove(pos)
        self.closed.append(trade)
        if journal_path:
            new = not os.path.exists(journal_path)
            with open(journal_path, "a", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(asdict(trade)))
                if new:
                    w.writeheader()
                w.writerow(asdict(trade))
        return trade

    def stats(self) -> dict:
        n = len(self.closed)
        wins = [t for t in self.closed if t.pnl > 0]
        losses = [t for t in self.closed if t.pnl <= 0]
        eq = self.equity()
        return {
            "trades": n,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / n if n else None,
            # If prices were perfectly fair, we'd win about as often as the average
            # entry price. Beating this number is the real test of an edge.
            "expected_win_rate": sum(t.entry_price for t in self.closed) / n if n else None,
            "avg_win": sum(t.pnl for t in wins) / len(wins) if wins else 0.0,
            "avg_loss": sum(t.pnl for t in losses) / len(losses) if losses else 0.0,
            "realised_pnl": sum(t.pnl for t in self.closed),
            "equity": eq,
            "return_pct": (eq / self.starting_bankroll - 1) * 100,
            "open_positions": len(self.positions),
            "cash": self.cash,
        }
