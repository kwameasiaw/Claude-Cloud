"""One stocks cycle: manage open trades, then look for dips to buy. Market hours only."""
from datetime import datetime, timezone

from ..agents import postmortem, risk
from ..config import Config
from ..portfolio import Portfolio, Position
from . import strategy
from .alpaca import AlpacaClient, configured


def _log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}Z] stocks: {msg}", flush=True)


def _held_days(pos: Position) -> float:
    opened = datetime.fromisoformat(pos.opened_at)
    return (datetime.now(timezone.utc) - opened).total_seconds() / 86400


def run_cycle(cfg: Config, client: AlpacaClient | None = None) -> Portfolio:
    pf = Portfolio.load(cfg.stocks_state_path, cfg.starting_bankroll)
    funnel = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if not configured() and client is None:
        funnel["skipped"] = "Alpaca keys not set (APCA_API_KEY_ID / APCA_API_SECRET_KEY)"
        _log(funnel["skipped"])
        pf.last_run = funnel
        pf.save(cfg.stocks_state_path)
        return pf
    client = client or AlpacaClient()
    try:
        clock = client.clock()
        symbols = sorted(set(strategy.UNIVERSE) | {p.market_id for p in pf.positions})
        bars = client.daily_bars(symbols)
        quotes = client.latest_quotes(symbols)
    except Exception as e:
        funnel["skipped"] = f"Alpaca unavailable: {e}"
        _log(funnel["skipped"])
        pf.last_run = funnel
        pf.save(cfg.stocks_state_path)
        return pf

    # Mark open trades to the bid; exit only while the market is open.
    closed = []
    for pos in list(pf.positions):
        q = quotes.get(pos.market_id)
        if not q:
            continue
        bid = q[0]
        pos.last_bid = round(bid, 4)
        if not clock.get("is_open"):
            continue
        why = strategy.exit_reason(bars.get(pos.market_id, []), bid, pos.stop_price, _held_days(pos))
        if why:
            t = pf.close(pos, bid, why, cfg.stocks_journal_path)
            closed.append(t)
            _log(f"SELL {pos.market_id} ({why}) @ {bid:.2f} -> P&L £{t.pnl:+.2f}")
    history = [vars(t) for t in pf.closed]
    for t in closed:
        if t.pnl < 0:
            rec = postmortem.run(vars(t), t.decision, history, cfg)
            _log(f"POSTMORTEM {rec['verdict']}: {t.market_id}")

    funnel.update(scanned=len(quotes), market_open=bool(clock.get("is_open")))
    if not clock.get("is_open"):
        funnel["skipped"] = "US market closed (open 14:30-21:00 UK time, weekdays)"
    elif risk.portfolio_halt(pf, cfg):
        funnel["skipped"] = risk.portfolio_halt(pf, cfg)
    else:
        avoid = postmortem.apply_lessons(cfg, postmortem.load_lessons(cfg))[1]
        signals = []
        for sym, (bid, ask) in quotes.items():
            if (ask - bid) / ask > 0.005:      # skip quotes with a spread over 0.5%
                continue
            s = strategy.evaluate(sym, bars.get(sym, []), ask)
            if s and s.sector not in avoid:
                signals.append(s)
        signals.sort(key=lambda s: s.rsi2)     # deepest dips first
        traded, blocked = 0, []
        for s in signals:
            rd = risk.check_stock(s.symbol, s.price, s.stop, pf, cfg, s.sector)
            if not rd.approved:
                blocked.append(f"{s.symbol}: {rd.reasons[-1]}")
                continue
            pos = Position(
                market_id=s.symbol, event_id=s.symbol, question=f"{s.name} ({s.symbol})",
                outcome="Long", token_id="", shares=round(rd.stake / s.price, 6),
                entry_price=s.price, stake=rd.stake, stop_price=s.stop,
                opened_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                url=f"https://www.google.com/finance/quote/{s.symbol.replace('.', '-')}",
                last_bid=quotes[s.symbol][0], tags=[s.sector],
                decision={"kind": "stock", "category": s.sector, "tags": [s.sector],
                          "stop_price": s.stop, "signal": s.reasons,
                          "risk": {"stake": rd.stake, "reasons": rd.reasons}},
            )
            pf.open(pos)
            traded += 1
            _log(f"BUY £{rd.stake:.2f} of {s.symbol} @ {s.price:.2f} (stop {s.stop:.2f}): "
                 + "; ".join(s.reasons))
        funnel.update(signals=len(signals), traded=traded, blocked_examples=blocked[:5])
    pf.last_run = funnel
    pf.snapshot()
    pf.save(cfg.stocks_state_path)
    return pf
