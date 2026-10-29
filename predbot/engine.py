"""One Polymarket cycle: manage open bets, then run the five-agent pipeline.

  1. Scan agent        filters every open market, flags odd ones
  2. Research agents   news / Reddit / X in parallel, scored by Claude
  3. Prediction agent  XGBoost (or rule) + Claude -> probability, edge, confidence
  4. Risk agent        Kelly sizing, limits, then a paper fill against the real order book
  5. Postmortem agents five reviews of every losing trade, lessons fed back into 1-4
"""
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import strategy
from .agents import postmortem, predict, research, risk, scan
from .config import Config
from .polymarket import PolymarketClient
from .portfolio import Portfolio, Position


def _log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}Z] {msg}", flush=True)


def manage_positions(pf: Portfolio, client: PolymarketClient, cfg: Config) -> list:
    """Settle, stop out or cash out open bets. Returns the trades closed this cycle."""
    now = datetime.now(timezone.utc)
    closed = []
    for pos in list(pf.positions):
        try:
            market = client.get_market(pos.market_id)
        except Exception as e:  # network hiccup: keep the position, try next cycle
            _log(f"could not refresh '{pos.question[:60]}': {e}")
            continue
        if market is None:
            continue
        if market.end_date and not pos.closes_at:
            pos.closes_at = market.end_date.isoformat(timespec="seconds")

        settle = market.settlement_price(pos.token_id)
        if settle is not None:
            t = pf.close(pos, settle, "resolved " + ("WIN" if settle else "LOSS"), cfg.journal_path)
            _log(f"SETTLED {t.reason}: {pos.question[:70]} -> P&L £{t.pnl:+.2f}")
            closed.append(t)
            continue

        o = market.outcome(pos.token_id)
        if o is None:
            continue
        net_bid = round(o.bid - market.taker_fee(o.bid), 4)
        pos.last_bid = net_bid
        reason = strategy.exit_reason(pos.entry_price, o.bid,
                                      strategy.hours_to_close(market, now), cfg)
        if reason and market.accepting_orders:
            t = pf.close(pos, net_bid, reason, cfg.journal_path)
            _log(f"EXIT {reason} @ {o.bid:.3f}: {pos.question[:70]} -> P&L £{t.pnl:+.2f}")
            closed.append(t)
    return closed


def run_postmortems(pf: Portfolio, closed: list, cfg: Config) -> None:
    history = [vars(t) for t in pf.closed]
    for t in closed:
        if t.pnl < 0:
            rec = postmortem.run(vars(t), t.decision, history, cfg)
            _log(f"POSTMORTEM {rec['verdict']}: {t.question[:60]}"
                 + (f"; new lesson(s): {', '.join(rec['rules_activated'])}" if rec["rules_activated"] else ""))


def open_new_positions(pf: Portfolio, client: PolymarketClient, cfg: Config) -> dict:
    funnel = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if len(pf.positions) >= cfg.max_open_positions:
        _log(f"at max {cfg.max_open_positions} open bets; pipeline skipped")
        funnel["skipped"] = f"all {cfg.max_open_positions} bet slots in use"
        return funnel
    halt = risk.portfolio_halt(pf, cfg)
    if halt:
        _log(f"risk halt: {halt}")
        funnel["skipped"] = halt
        return funnel

    lessons = postmortem.load_lessons(cfg)
    cfg_eff, avoid_tags, caution = postmortem.apply_lessons(cfg, lessons)

    # 1. Scan
    markets = client.list_open_markets()
    sr = scan.run(markets, cfg_eff, avoid_tags, client.get_event_tags if avoid_tags else None)
    sr.candidates.sort(key=lambda c: c.market.liquidity, reverse=True)   # deepest books first
    cands = [c for c in sr.candidates if not pf.holds(c.market.id, c.market.event_id)][:cfg.research_top]
    funnel.update(scanned=sr.scanned, flagged=len(sr.flagged), passed_filters=sr.passed_filters,
                  candidates=len(sr.candidates), researched=len(cands),
                  flag_examples=[f"{m.question[:70]}: {why}" for m, why in sr.flagged[:5]])
    _log(f"scan: {sr.scanned} markets, {len(sr.flagged)} flagged, {len(sr.candidates)} candidates")
    if not cands:
        funnel.update(predicted_fire=0, approved=0, traded=0)
        return funnel

    # 2. Research (parallel across candidates and sources)
    found = research.run(cands, cfg_eff)
    ok = sorted({s for r in found.values() for s in r.sources_ok})
    funnel["sources"] = ok
    _log(f"research: sources working: {', '.join(ok) or 'none'}")

    # 3. Predict
    now = int(time.time())

    def hist(c):
        try:
            return client.price_history(c.outcome.token_id, now - 8 * 86400, now)
        except Exception:
            return []
    with ThreadPoolExecutor(max_workers=cfg.research_workers) as pool:
        histories = list(pool.map(hist, cands))
    preds = [predict.predict(c, found[c.market.id], h, cfg_eff, caution) for c, h in zip(cands, histories)]
    firing = sorted([p for p in preds if p.fire], key=lambda p: p.edge * p.confidence, reverse=True)
    funnel["predicted_fire"] = len(firing)
    funnel["model"] = preds[0].method if preds else ""
    _log(f"predict: {len(firing)} of {len(preds)} clear the edge and confidence bars")

    # 4. Risk, then paper fill
    approved = traded = 0
    blocked = []
    for p in firing:
        if len(pf.positions) >= cfg.max_open_positions:
            break
        c, m, o = p.candidate, p.candidate.market, p.candidate.outcome
        try:
            tags = client.get_event_tags(m.event_id)
            asks = client.get_asks(o.token_id)
        except Exception as e:
            _log(f"skip (market data unavailable): {m.question[:60]} ({e})")
            continue
        rd = risk.check_bet(p.p_final, p.cost, pf, cfg_eff, tags)
        if not rd.approved:
            blocked.append(f"{m.question[:60]}: {rd.reasons[-1]}")
            _log(f"risk blocked: {m.question[:60]} ({rd.reasons[-1]})")
            continue
        approved += 1
        fill = strategy.simulate_fill(asks, rd.stake)
        if fill is None:
            _log(f"skip (book too thin for £{rd.stake:.2f}): {m.question[:60]}")
            continue
        _, avg = fill
        cost = avg + m.taker_fee(avg)
        if avg - o.ask > cfg.max_book_slippage or p.p_final - cost < cfg_eff.min_edge:
            _log(f"skip (fill {avg:.3f} eats the edge): {m.question[:60]}")
            continue
        stop = strategy.stop_price(cost, cfg)
        decision = {
            "category": m.category, "tags": tags, "scan": c.notes, "stop_price": stop,
            "research": found[m.id].to_dict(), "prediction": p.to_dict(),
            "risk": {"stake": rd.stake, "kelly": round(rd.kelly_fraction, 4), "reasons": rd.reasons},
        }
        pos = Position(
            market_id=m.id, event_id=m.event_id, question=m.question, outcome=o.name,
            token_id=o.token_id, shares=round(rd.stake / cost, 4), entry_price=round(cost, 4),
            stake=rd.stake, stop_price=stop,
            opened_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            url=m.url, last_bid=round(o.bid - m.taker_fee(o.bid), 4), tags=tags,
            closes_at=m.end_date.isoformat(timespec="seconds") if m.end_date else "",
            decision=decision,
        )
        pf.open(pos)
        traded += 1
        _log(f"BUY £{rd.stake:.2f} of '{o.name}' @ {avg:.3f} (stop {stop:.3f}): {m.question[:70]}")
        _log("    why: " + "; ".join(p.reasons) + " | " + "; ".join(rd.reasons))
    funnel.update(approved=approved, traded=traded, blocked_examples=blocked[:5])
    return funnel


def run_cycle(cfg: Config, client: PolymarketClient | None = None) -> Portfolio:
    client = client or PolymarketClient()
    pf = Portfolio.load(cfg.state_path, cfg.starting_bankroll)
    closed = manage_positions(pf, client, cfg)
    pf.save(cfg.state_path)
    try:
        run_postmortems(pf, closed, cfg)
        pf.last_run = open_new_positions(pf, client, cfg)
    finally:
        pf.snapshot()
        pf.save(cfg.state_path)
    return pf
