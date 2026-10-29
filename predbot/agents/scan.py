"""Step 1: Scan agent. Filters every open market and flags anything that looks off."""
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .. import strategy
from ..config import Config
from ..polymarket import Market, Outcome


@dataclass
class Candidate:
    market: Market
    outcome: Outcome           # the favourite we'd buy
    notes: list[str] = field(default_factory=list)


@dataclass
class ScanResult:
    scanned: int = 0
    passed_filters: int = 0
    flagged: list[tuple[Market, str]] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)


def flag(market: Market, cfg: Config) -> str | None:
    """A reason to distrust this market's price right now, or None."""
    o = market.outcomes[0]
    if abs(o.day_change) >= cfg.flag_day_move:
        return f"price swung {o.day_change*100:+.0f}c in 24h"
    if o.ask - o.bid >= cfg.flag_spread:
        return f"spread {o.ask - o.bid:.2f} is unusually wide"
    return None


def run(markets: list[Market], cfg: Config, avoid_tags: set[str] = frozenset(),
        tags_for=None, now: datetime | None = None, mode: str = "favourite") -> ScanResult:
    """mode "favourite": the favourite of each event, one per event.
    mode "value": every outcome in the price band; the engine later keeps the side
    the calibration data rates best, one per event."""
    now = now or datetime.now(timezone.utc)
    res = ScanResult(scanned=len(markets))
    seen_events = set()
    for m in markets:
        if not m.outcomes:
            continue
        why = flag(m, cfg)
        if why:
            res.flagged.append((m, why))
            continue
        if strategy.rejection(m, cfg, now):
            continue
        res.passed_filters += 1
        options = m.outcomes if mode == "value" else [max(m.outcomes, key=lambda o: o.ask)]
        options = [o for o in options
                   if cfg.min_entry_price <= o.ask <= cfg.max_entry_price
                   and o.day_change >= -cfg.max_day_drop and o.week_change >= -cfg.max_week_drop]
        if not options:
            continue
        if mode != "value" and m.event_id in seen_events:
            continue
        if avoid_tags and tags_for and avoid_tags & set(tags_for(m.event_id)):
            res.flagged.append((m, "topic blocked by an earlier postmortem lesson"))
            continue
        seen_events.add(m.event_id)
        for o in options:
            res.candidates.append(Candidate(m, o, [
                f"'{o.name}' at {o.ask:.2f}", f"liq ${m.liquidity:,.0f}",
                f"vol24h ${m.volume_24h:,.0f}", f"closes in {strategy.hours_to_close(m, now)/24:.1f}d"]))
    return res
