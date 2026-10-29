import json
import os
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from predbot import calibration, strategy
from predbot.agents import postmortem, research, risk, scan
from predbot.config import Config
from predbot.dashboard import render
from predbot.engine import run_cycle
from predbot.polymarket import parse_market
from predbot.portfolio import Portfolio
from predbot.stocks import engine as stock_engine
from predbot.stocks import strategy as stock_strategy

NOW = datetime.now(timezone.utc)
research.SOURCES = {}          # never touch the network in tests


def raw_market(mid="1", bid=0.70, ask=0.71, days=5, liq=50_000, vol=20_000,
               day=0.0, week=0.02, closed=False, final=None, event="e1"):
    return {
        "id": mid, "question": f"Market {mid}?", "slug": f"m{mid}",
        "events": [{"id": event}],
        "endDate": (NOW + timedelta(days=days)).isoformat().replace("+00:00", "Z"),
        "liquidityNum": liq, "volume24hr": vol,
        "active": True, "closed": closed, "acceptingOrders": not closed,
        "outcomes": json.dumps(["Yes", "No"]),
        "clobTokenIds": json.dumps([f"{mid}-yes", f"{mid}-no"]),
        "outcomePrices": json.dumps(final or [str((bid + ask) / 2), str(1 - (bid + ask) / 2)]),
        "bestBid": bid, "bestAsk": ask,
        "oneDayPriceChange": day, "oneWeekPriceChange": week, "lastTradePrice": bid,
    }


class FakeClient:
    def __init__(self, markets, tags=None):
        self.markets = {m["id"]: m for m in markets}
        self.tags = tags or {}

    def get_event_tags(self, event_id):
        return self.tags.get(event_id, [])

    def list_open_markets(self):
        return [m for m in map(parse_market, self.markets.values()) if m and not m.closed]

    def get_market(self, mid):
        return parse_market(self.markets[mid])

    def price_history(self, token_id, start=None, end=None):
        return []

    def get_asks(self, token_id):
        mid, side = token_id.split("-")
        m = self.markets[mid]
        ask = m["bestAsk"] if side == "yes" else round(1 - m["bestBid"], 4)
        return [(ask, 1000.0), (ask + 0.01, 1000.0)]


def temp_cfg(d: str, favourite_estimate: float = 0.80) -> Config:
    """Config writing into a temp dir, with a calibration table saying 70-75p wins ~80%."""
    cal = os.path.join(d, "cal.json")
    calibration.save({"bucket": 0.05, "shrink": 60, "buckets": {
        "14": {"n": 200, "win_rate": favourite_estimate, "avg_price": 0.705, "estimate": favourite_estimate}}}, cal)
    j = lambda name: os.path.join(d, name)
    return replace(Config(), state_path=j("s.json"), journal_path=j("j.csv"),
                   dashboard_path=j("d.html"), stocks_state_path=j("ss.json"),
                   stocks_journal_path=j("sj.csv"), postmortem_path=j("pm.jsonl"),
                   lessons_path=j("lessons.json"), calibration_path=cal,
                   model_path=j("none.json"), model_meta_path=j("none_meta.json"))


class ParseTest(unittest.TestCase):
    def test_no_side_mirrors_yes_book(self):
        m = parse_market(raw_market(bid=0.30, ask=0.31, week=-0.04))
        no = m.outcomes[1]
        self.assertAlmostEqual(no.bid, 0.69)
        self.assertAlmostEqual(no.ask, 0.70)
        self.assertAlmostEqual(no.week_change, 0.04)

    def test_settlement(self):
        m = parse_market(raw_market(closed=True, final=["1", "0"]))
        self.assertEqual(m.settlement_price("1-yes"), 1.0)
        self.assertEqual(m.settlement_price("1-no"), 0.0)


class ScanTest(unittest.TestCase):
    cfg = Config()

    def test_picks_favourite_either_side(self):
        res = scan.run([parse_market(raw_market(bid=0.27, ask=0.28))], self.cfg)
        self.assertEqual(res.candidates[0].outcome.name, "No")

    def test_flags_wild_moves_and_wide_spreads(self):
        res = scan.run([parse_market(raw_market(mid="1", day=0.15, event="a")),
                        parse_market(raw_market(mid="2", bid=0.66, ask=0.71, event="b"))], self.cfg)
        self.assertEqual(len(res.flagged), 2)
        self.assertFalse(res.candidates)

    def test_rejections(self):
        for kw in [dict(liq=1000), dict(vol=100), dict(days=0.5), dict(days=90),
                   dict(bid=0.90, ask=0.91), dict(bid=0.50, ask=0.51), dict(day=-0.05), dict(week=-0.10)]:
            with self.subTest(**kw):
                self.assertFalse(scan.run([parse_market(raw_market(**kw))], self.cfg).candidates)

    def test_one_candidate_per_event(self):
        ms = [parse_market(raw_market(mid=str(i), event="same")) for i in range(3)]
        self.assertEqual(len(scan.run(ms, self.cfg).candidates), 1)

    def test_exit_rules(self):
        self.assertEqual(strategy.exit_reason(0.70, 0.56, 48, self.cfg), "stop-loss")
        self.assertEqual(strategy.exit_reason(0.70, 0.95, 48, self.cfg), "take-profit")
        self.assertIsNone(strategy.exit_reason(0.70, 0.65, 48, self.cfg))

    def test_fill_walks_book(self):
        shares, avg = strategy.simulate_fill([(0.70, 10), (0.72, 100)], 10.0)
        self.assertAlmostEqual(shares * avg, 10.0)
        self.assertTrue(0.70 < avg < 0.72)
        self.assertIsNone(strategy.simulate_fill([(0.70, 1)], 10.0))

    def test_theme_clash(self):
        held = [["midterms", "politics"], ["midterms", "texas"]]
        self.assertEqual(strategy.theme_clash(["midterms", "ohio"], held, self.cfg), "midterms")
        self.assertIsNone(strategy.theme_clash(["politics", "nba"], held, self.cfg))


class CalibrationTest(unittest.TestCase):
    def test_one_snapshot_per_market_and_shrinkage(self):
        # 10 markets priced ~72p that all lost; each has several snapshots in the same bucket.
        groups = [[[0, [0.72, 0, d, 0, 0, 0, 0, 0, 0, 0], 0, 0.72] for d in (1, 5, 7)] for _ in range(10)]
        b = calibration.build(groups)["buckets"]["14"]
        self.assertEqual(b["n"], 10)
        self.assertEqual(b["win_rate"], 0.0)
        self.assertTrue(0.5 < b["estimate"] < 0.72)   # pulled toward price, not to zero

    def test_estimate_applies_bucket_bias(self):
        t = {"bucket": 0.05, "buckets": {"14": {"n": 100, "avg_price": 0.72, "estimate": 0.68}}}
        p, n = calibration.estimate(t, 0.74)
        self.assertAlmostEqual(p, 0.70)
        self.assertEqual(n, 100)


class RiskTest(unittest.TestCase):
    def setUp(self):
        self.cfg = Config()
        self.pf = Portfolio(cash=100, starting_bankroll=100)

    def test_kelly(self):
        self.assertAlmostEqual(risk.kelly(0.80, 0.70), (0.80 - 0.70) / 0.30)
        self.assertEqual(risk.kelly(0.60, 0.70), 0.0)

    def test_sizes_small_edge_small_and_caps_big_edge(self):
        small = risk.check_bet(0.73, 0.71, self.pf, self.cfg, [])
        self.assertFalse(small.approved)                  # quarter-Kelly < £2 minimum
        big = risk.check_bet(0.95, 0.70, self.pf, self.cfg, [])
        self.assertTrue(big.approved)
        self.assertAlmostEqual(big.stake, 10.0)           # capped at 10% of the pot

    def test_drawdown_halt(self):
        self.pf.cash = 70
        self.assertIn("below its start", risk.portfolio_halt(self.pf, self.cfg))

    def test_stock_sizing_never_risks_more_than_1_5_percent(self):
        tight = risk.check_stock("AAPL", 100, 95, self.pf, self.cfg, "tech")
        self.assertAlmostEqual(tight.stake, 10.0)        # 10% cap binds first...
        self.assertLessEqual(tight.stake * 0.05, 1.5)    # ...so a stop-out costs only 0.5%
        wide = risk.check_stock("AAPL", 100, 80, self.pf, self.cfg, "tech")
        self.assertAlmostEqual(wide.stake * 0.20, 1.5)   # wide stop: sized to lose 1.5%


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.cfg = temp_cfg(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def test_full_lifecycle_with_postmortem(self):
        client = FakeClient([raw_market(mid=str(i), event=f"e{i}") for i in range(8)])
        pf = run_cycle(self.cfg, client)
        self.assertEqual(len(pf.positions), self.cfg.max_open_positions)
        self.assertLessEqual(pf.positions[0].stake, 10.0)
        self.assertIn("prediction", pf.positions[0].decision)
        self.assertEqual(pf.last_run["traded"], self.cfg.max_open_positions)

        held = [p.market_id for p in pf.positions]
        client.markets[held[0]].update(closed=True, outcomePrices=json.dumps(["1", "0"]))
        client.markets[held[1]].update(closed=True, outcomePrices=json.dumps(["0", "1"]))
        client.markets[held[2]].update(bestBid=0.40, bestAsk=0.41)
        pf = run_cycle(self.cfg, client)

        self.assertEqual(sorted(t.reason for t in pf.closed), ["resolved LOSS", "resolved WIN", "stop-loss"])
        pms = postmortem.recent(self.cfg)
        self.assertEqual(len(pms), 2)                       # one per losing trade
        self.assertEqual(len(pms[0]["reviews"]), 5)         # five reviewers each
        self.assertEqual(len(Portfolio.load(self.cfg.state_path, 100).history), 3)

    def test_no_edge_no_trade(self):
        cfg = temp_cfg(self.dir.name, favourite_estimate=0.65)   # favourites overpriced
        pf = run_cycle(cfg, FakeClient([raw_market()]))
        self.assertFalse(pf.positions)
        self.assertEqual(pf.last_run["predicted_fire"], 0)

    def test_caps_related_bets(self):
        client = FakeClient([raw_market(mid=str(i), event=f"e{i}") for i in range(4)],
                            {f"e{i}": ["midterms"] for i in range(4)})
        pf = run_cycle(self.cfg, client)
        self.assertEqual(len(pf.positions), self.cfg.max_per_theme)

    def test_dashboard_renders_both_pots(self):
        run_cycle(self.cfg, FakeClient([raw_market()]))
        page = render(self.cfg)
        self.assertIn("<title>Paper Pot</title>", page)
        self.assertIn("Stocks pot", page)
        self.assertIn("Markets scanned", page)


class PostmortemTest(unittest.TestCase):
    def test_lesson_activates_only_after_repeats(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = temp_cfg(d)
            trade = {"question": "Q?", "outcome": "Yes", "pnl": -5.0, "reason": "resolved LOSS",
                     "entry_price": 0.75, "exit_price": 0.0, "stake": 5.0}
            decision = {"category": "sports", "tags": [], "research": {"items": 4, "stance": -0.6},
                        "prediction": {"p_final": 0.78, "cost": 0.75}}
            for i in range(3):
                rec = postmortem.run(trade, decision, [], cfg)
                self.assertEqual(bool(rec["rules_activated"]), i == 2)
            tightened, _, _ = postmortem.apply_lessons(cfg, postmortem.load_lessons(cfg))
            self.assertAlmostEqual(tightened.min_edge, cfg.min_edge + 0.005)


def bars_with_dip(n=260, start=100.0):
    bars, price = [], start
    for i in range(n):
        price *= 1.002
        bars.append({"t": i, "o": price, "h": price * 1.01, "l": price * 0.99, "c": price, "v": 1})
    for drop in (0.97, 0.96):               # two sharp down days
        price *= drop
        bars.append({"t": len(bars), "o": price, "h": price * 1.01, "l": price * 0.99, "c": price, "v": 1})
    return bars


class FakeAlpaca:
    def __init__(self):
        self.bars = {"AAPL": bars_with_dip()}
        last = self.bars["AAPL"][-1]["c"]
        self.quotes = {"AAPL": (round(last * 0.9995, 2), round(last * 1.0005, 2))}

    def clock(self):
        return {"is_open": True}

    def daily_bars(self, symbols):
        return {s: self.bars.get(s, []) for s in symbols}

    def latest_quotes(self, symbols):
        return {s: q for s, q in self.quotes.items() if s in symbols}


class StocksTest(unittest.TestCase):
    def test_signal(self):
        bars = bars_with_dip()
        s = stock_strategy.evaluate("AAPL", bars, bars[-1]["c"])
        self.assertIsNotNone(s)
        self.assertLess(s.rsi2, 10)
        self.assertLess(s.stop, s.price)
        self.assertIsNone(stock_strategy.evaluate("AAPL", bars[:-2], bars[-3]["c"]))   # no dip

    def test_buy_then_sell_on_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            cfg, fake = temp_cfg(d), FakeAlpaca()
            pf = stock_engine.run_cycle(cfg, fake)
            self.assertEqual([p.market_id for p in pf.positions], ["AAPL"])
            self.assertLessEqual(pf.positions[0].stake, 10.0)
            recovered = fake.bars["AAPL"][-3]["c"]
            fake.quotes["AAPL"] = (recovered, recovered * 1.0005)
            pf = stock_engine.run_cycle(cfg, fake)
            self.assertEqual([t.reason for t in pf.closed], ["take-profit"])
            self.assertGreater(pf.closed[0].pnl, 0)

    def test_skips_without_keys(self):
        with tempfile.TemporaryDirectory() as d:
            env = {k: os.environ.pop(k) for k in ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY") if k in os.environ}
            try:
                pf = stock_engine.run_cycle(temp_cfg(d))
                self.assertIn("Alpaca keys not set", pf.last_run["skipped"])
            finally:
                os.environ.update(env)


if __name__ == "__main__":
    unittest.main()
