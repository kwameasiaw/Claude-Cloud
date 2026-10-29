"""One trading cycle: manage open positions, then look for new trades."""
from datetime import datetime, timezone

from . import strategy
from .config import Config
from .polymarket import PolymarketClient
from .portfolio import Portfolio, Position


def _log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}Z] {msg}", flush=True)


def manage_positions(pf: Portfolio, client: PolymarketClient, cfg: Config) -> None:
    now = datetime.now(timezone.utc)
    for pos in list(pf.positions):
        try:
            market = client.get_market(pos.market_id)
        except Exception as e:  # network hiccup: keep the position, try next cycle
            _log(f"could not refresh '{pos.question[:60]}': {e}")
            continue
        if market is None:
            continue

        settle = market.settlement_price(pos.token_id)
        if settle is not None:
            t = pf.close(pos, settle, "resolved " + ("WIN" if settle else "LOSS"), cfg.journal_path)
            _log(f"SETTLED {t.reason}: {pos.question[:70]} -> P&L £{t.pnl:+.2f}")
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


def open_new_positions(pf: Portfolio, client: PolymarketClient, cfg: Config,
                       verbose: bool = True) -> None:
    if len(pf.positions) >= cfg.max_open_positions:
        _log(f"at max {cfg.max_open_positions} open positions; not looking for new trades")
        return
    markets = client.list_open_markets()
    signals = strategy.scan(markets, cfg)
    _log(f"scanned {len(markets)} markets, {len(signals)} pass every filter")

    for sig in signals:
        if len(pf.positions) >= cfg.max_open_positions:
            break
        m, o = sig.market, sig.outcome
        if pf.holds(m.id, m.event_id):
            continue
        stake = round(min(pf.cash, pf.equity() * cfg.stake_fraction), 2)
        if stake < cfg.min_stake:
            _log("not enough free cash for a minimum-size trade")
            break
        try:
            tags = client.get_event_tags(m.event_id)
            asks = client.get_asks(o.token_id)
        except Exception as e:
            _log(f"skip (market data unavailable): {m.question[:60]} ({e})")
            continue
        clash = strategy.theme_clash(tags, [p.tags for p in pf.positions], cfg)
        if clash:
            _log(f"skip (already {cfg.max_per_theme} bets on '{clash}'): {m.question[:60]}")
            continue
        fill = strategy.simulate_fill(asks, stake)
        if fill is None:
            _log(f"skip (book too thin for £{stake:.2f}): {m.question[:60]}")
            continue
        _, avg = fill
        cost = avg + m.taker_fee(avg)   # all-in price per share
        if avg - o.ask > cfg.max_book_slippage or sig.fair_value - cost < cfg.min_edge:
            _log(f"skip (fill {avg:.3f} eats the edge): {m.question[:60]}")
            continue
        pos = Position(
            market_id=m.id, event_id=m.event_id, question=m.question, outcome=o.name,
            token_id=o.token_id, shares=round(stake / cost, 4), entry_price=round(cost, 4),
            stake=stake, stop_price=strategy.stop_price(cost, cfg),
            opened_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            url=m.url, last_bid=round(o.bid - m.taker_fee(o.bid), 4), tags=tags,
        )
        pf.open(pos)
        _log(f"BUY £{stake:.2f} of '{o.name}' @ {avg:.3f} (stop {pos.stop_price:.3f}, "
             f"target {cfg.take_profit_price:.2f}): {m.question[:70]}")
        if verbose:
            _log("    why: " + "; ".join(sig.reasons))


def run_cycle(cfg: Config, client: PolymarketClient | None = None) -> Portfolio:
    client = client or PolymarketClient()
    pf = Portfolio.load(cfg.state_path, cfg.starting_bankroll)
    manage_positions(pf, client, cfg)
    pf.save(cfg.state_path)
    try:
        open_new_positions(pf, client, cfg)
    finally:
        pf.save(cfg.state_path)
    return pf
