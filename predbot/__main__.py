"""CLI: python -m predbot {scan,run,loop,report,reset}"""
import argparse
import os
import time
from datetime import datetime, timezone

from . import strategy
from .config import Config
from .engine import run_cycle
from .polymarket import PolymarketClient
from .portfolio import Portfolio


def cmd_scan(cfg: Config) -> None:
    markets = PolymarketClient().list_open_markets()
    now = datetime.now(timezone.utc)
    signals = strategy.scan(markets, cfg, now)
    print(f"{len(markets)} markets scanned, {len(signals)} tradeable (no trades placed)\n")
    for s in signals[:15]:
        print(f"* {s.market.question}\n    {'; '.join(s.reasons)}\n    {s.market.url}")


def cmd_report(cfg: Config) -> None:
    pf = Portfolio.load(cfg.state_path, cfg.starting_bankroll)
    st = pf.stats()
    pct = lambda v: "n/a" if v is None else f"{v*100:.1f}%"
    print(f"Paper bankroll  start £{pf.starting_bankroll:.2f}  ->  equity £{st['equity']:.2f} "
          f"({st['return_pct']:+.1f}%)   cash £{st['cash']:.2f}")
    print(f"Closed trades   {st['trades']}  (W {st['wins']} / L {st['losses']})   "
          f"win rate {pct(st['win_rate'])}   break-even win rate {pct(st['expected_win_rate'])}")
    print(f"Avg win £{st['avg_win']:+.2f}   avg loss £{st['avg_loss']:+.2f}   "
          f"realised P&L £{st['realised_pnl']:+.2f}")
    if st["trades"] < 30:
        print("(fewer than 30 closed trades: too few to judge the strategy yet)")
    if pf.positions:
        print("\nOpen positions:")
        for p in pf.positions:
            bid = p.last_bid if p.last_bid is not None else p.entry_price
            print(f"  £{p.stake:6.2f} {p.outcome:>4} @ {p.entry_price:.3f}  now {bid:.3f}  "
                  f"stop {p.stop_price:.3f}  {p.question[:60]}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="predbot", description="Polymarket paper-trading bot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan", help="show current opportunities without trading")
    sub.add_parser("run", help="run one trading cycle")
    lp = sub.add_parser("loop", help="run cycles forever")
    lp.add_argument("--minutes", type=float, default=15, help="minutes between cycles")
    sub.add_parser("report", help="show paper P&L and win rate")
    sub.add_parser("reset", help="delete paper state and journal, start again at £100")
    args = ap.parse_args()
    cfg = Config()

    if args.cmd == "scan":
        cmd_scan(cfg)
    elif args.cmd == "run":
        run_cycle(cfg)
        cmd_report(cfg)
    elif args.cmd == "loop":
        while True:
            try:
                run_cycle(cfg)
            except Exception as e:  # keep looping through network errors
                print(f"cycle failed: {e}", flush=True)
            time.sleep(args.minutes * 60)
    elif args.cmd == "report":
        cmd_report(cfg)
    elif args.cmd == "reset":
        for path in (cfg.state_path, cfg.journal_path):
            if os.path.exists(path):
                os.remove(path)
        print(f"Reset. Next run starts with £{cfg.starting_bankroll:.2f} paper money.")


if __name__ == "__main__":
    main()
