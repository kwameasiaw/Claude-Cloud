import json
import os
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from predbot import strategy
from predbot.config import Config
from predbot.engine import run_cycle
from predbot.polymarket import parse_market
from predbot.portfolio import Portfolio

NOW = datetime.now(timezone.utc)


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

    def get_asks(self, token_id):
        mid, side = token_id.split("-")
        m = self.markets[mid]
        ask = m["bestAsk"] if side == "yes" else round(1 - m["bestBid"], 4)
        return [(ask, 1000.0), (ask + 0.01, 1000.0)]


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


class StrategyTest(unittest.TestCase):
    cfg = Config()

    def test_buys_liquid_steady_favourite(self):
        sig = strategy.evaluate(parse_market(raw_market()), self.cfg)
        self.assertIsNotNone(sig)
        self.assertEqual(sig.outcome.name, "Yes")

    def test_picks_no_when_no_is_favourite(self):
        sig = strategy.evaluate(parse_market(raw_market(bid=0.27, ask=0.28)), self.cfg)
        self.assertEqual(sig.outcome.name, "No")

    def test_rejections(self):
        for kw in [dict(liq=1000), dict(vol=100), dict(ask=0.75), dict(days=0.5),
                   dict(days=90), dict(bid=0.90, ask=0.91), dict(bid=0.50, ask=0.51),
                   dict(day=-0.05), dict(week=-0.10)]:
            with self.subTest(**kw):
                self.assertIsNone(strategy.evaluate(parse_market(raw_market(**kw)), self.cfg))

    def test_one_trade_per_event(self):
        ms = [parse_market(raw_market(mid=str(i), event="same")) for i in range(3)]
        self.assertEqual(len(strategy.scan(ms, self.cfg)), 1)

    def test_fees_can_kill_the_edge(self):
        raw = raw_market(bid=0.76, ask=0.77, week=0.0)
        self.assertIsNotNone(strategy.evaluate(parse_market(raw), self.cfg))
        raw.update(feesEnabled=True, feeSchedule={"rate": 0.07, "exponent": 1})
        self.assertIsNone(strategy.evaluate(parse_market(raw), self.cfg))

    def test_theme_clash(self):
        held = [["midterms", "politics"], ["midterms", "texas"]]
        self.assertEqual(strategy.theme_clash(["midterms", "ohio"], held, self.cfg), "midterms")
        self.assertIsNone(strategy.theme_clash(["politics", "nba"], held, self.cfg))

    def test_exit_rules(self):
        self.assertEqual(strategy.exit_reason(0.70, 0.56, 48, self.cfg), "stop-loss")
        self.assertEqual(strategy.exit_reason(0.70, 0.95, 48, self.cfg), "take-profit")
        self.assertIsNone(strategy.exit_reason(0.70, 0.65, 48, self.cfg))

    def test_fill_walks_book(self):
        shares, avg = strategy.simulate_fill([(0.70, 10), (0.72, 100)], 10.0)
        self.assertAlmostEqual(shares * avg, 10.0)
        self.assertTrue(0.70 < avg < 0.72)
        self.assertIsNone(strategy.simulate_fill([(0.70, 1)], 10.0))


class EngineTest(unittest.TestCase):
    def test_caps_related_bets(self):
        markets = [raw_market(mid=str(i), event=f"e{i}") for i in range(4)]
        client = FakeClient(markets, {f"e{i}": ["midterms"] for i in range(4)})
        pf = run_cycle(self.cfg, client)
        self.assertEqual(len(pf.positions), self.cfg.max_per_theme)

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.cfg = replace(Config(), state_path=os.path.join(self.dir.name, "s.json"),
                           journal_path=os.path.join(self.dir.name, "j.csv"),
                           dashboard_path=os.path.join(self.dir.name, "d.html"))

    def tearDown(self):
        self.dir.cleanup()

    def test_full_lifecycle(self):
        markets = [raw_market(mid=str(i), event=f"e{i}") for i in range(8)]
        client = FakeClient(markets)
        pf = run_cycle(self.cfg, client)
        self.assertEqual(len(pf.positions), self.cfg.max_open_positions)
        self.assertEqual(len({p.event_id for p in pf.positions}), len(pf.positions))
        self.assertAlmostEqual(pf.positions[0].stake, 10.0)       # 10% of £100
        self.assertAlmostEqual(pf.equity(), 100.0, delta=1.0)

        held = [p.market_id for p in pf.positions]
        # One wins, one loses, one crashes through its stop.
        client.markets[held[0]].update(closed=True, outcomePrices=json.dumps(["1", "0"]))
        client.markets[held[1]].update(closed=True, outcomePrices=json.dumps(["0", "1"]))
        client.markets[held[2]].update(bestBid=0.40, bestAsk=0.41)
        pf = run_cycle(self.cfg, client)

        reasons = sorted(t.reason for t in pf.closed)
        self.assertEqual(reasons, ["resolved LOSS", "resolved WIN", "stop-loss"])
        st = pf.stats()
        self.assertEqual((st["wins"], st["losses"]), (1, 2))
        self.assertTrue(os.path.exists(self.cfg.journal_path))
        # State survives a reload.
        again = Portfolio.load(self.cfg.state_path, 100)
        self.assertAlmostEqual(again.cash, pf.cash)
        self.assertEqual(len(again.history), 3)   # seeded start + one per cycle
        with open(self.cfg.dashboard_path) as f:
            page = f.read()
        self.assertIn("<title>Paper Pot</title>", page)
        self.assertIn("Sold at stop-loss", page)
        self.assertIn('id="pot-chart"', page)


if __name__ == "__main__":
    unittest.main()
