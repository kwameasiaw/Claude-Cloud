"""CLI: python -m predbot {scan,run,loop,report,dashboard,train,reset}"""
import argparse
import json
import os
import time

from . import engine
from .agents import scan
from .config import Config
from .dashboard import write_dashboard
from .polymarket import PolymarketClient
from .portfolio import Portfolio
from .stocks import engine as stock_engine


def cmd_scan(cfg: Config) -> None:
    res = scan.run(PolymarketClient().list_open_markets(), cfg)
    print(f"{res.scanned} markets scanned, {len(res.flagged)} flagged, "
          f"{len(res.candidates)} candidates (no research, no trades)\n")
    for m, why in res.flagged[:5]:
        print(f"! flagged: {m.question[:70]} ({why})")
    for c in res.candidates[:15]:
        print(f"* {c.market.question}\n    {'; '.join(c.notes)}\n    {c.market.url}")


def _report(name: str, pf: Portfolio) -> None:
    st = pf.stats()
    pct = lambda v: "n/a" if v is None else f"{v*100:.1f}%"
    print(f"== {name} ==")
    print(f"Pot  start £{pf.starting_bankroll:.2f}  ->  £{st['equity']:.2f} "
          f"({st['return_pct']:+.1f}%)   cash £{st['cash']:.2f}")
    print(f"Closed {st['trades']} (W {st['wins']} / L {st['losses']})   win rate {pct(st['win_rate'])}   "
          f"break-even {pct(st['break_even_win_rate'])}   realised £{st['realised_pnl']:+.2f}")
    for p in pf.positions:
        now = p.last_bid if p.last_bid is not None else p.entry_price
        print(f"  £{p.stake:6.2f} {p.outcome:>6} @ {p.entry_price:.3f}  now {now:.3f}  "
              f"stop {p.stop_price:.3f}  {p.question[:55]}")
    if pf.last_run.get("skipped"):
        print(f"  last run: {pf.last_run['skipped']}")


def cmd_report(cfg: Config) -> None:
    _report("Favourites pot", Portfolio.load(cfg.state_path, cfg.starting_bankroll))
    _report("Value pot", Portfolio.load(cfg.value_state_path, cfg.starting_bankroll))
    _report("Stocks pot", Portfolio.load(cfg.stocks_state_path, cfg.starting_bankroll))


def run_all(cfg: Config) -> None:
    jobs = [(pot, lambda pot=pot: engine.run_cycle(cfg, pot=pot)) for pot in engine.POTS]
    jobs.append(("stocks", lambda: stock_engine.run_cycle(cfg)))
    for name, job in jobs:
        try:
            job()
        except Exception as e:   # one pot failing must not stop the others
            print(f"{name} cycle failed: {e}", flush=True)
    write_dashboard(cfg)


def main() -> None:
    ap = argparse.ArgumentParser(prog="predbot", description="Paper-trading bot: Polymarket + US stocks")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan", help="show current Polymarket candidates without trading")
    sub.add_parser("run", help="run one cycle for all three pots and rebuild the dashboard")
    lp = sub.add_parser("loop", help="run cycles forever")
    lp.add_argument("--minutes", type=float, default=60, help="minutes between cycles")
    sub.add_parser("report", help="show all three pots")
    sub.add_parser("dashboard", help="rebuild dashboard.html from saved state")
    sub.add_parser("train", help="retrain the XGBoost calibration model on resolved markets")
    rp = sub.add_parser("reset", help="delete a pot's state and start again at £100")
    rp.add_argument("pot", choices=["favourites", "value", "stocks"])
    args = ap.parse_args()
    cfg = Config()

    if args.cmd == "scan":
        cmd_scan(cfg)
    elif args.cmd == "run":
        run_all(cfg)
        cmd_report(cfg)
    elif args.cmd == "loop":
        while True:
            run_all(cfg)
            time.sleep(args.minutes * 60)
    elif args.cmd == "report":
        cmd_report(cfg)
    elif args.cmd == "dashboard":
        write_dashboard(cfg)
        print(f"Wrote {cfg.dashboard_path}")
    elif args.cmd == "train":
        from .train import train
        print(json.dumps(train(cfg), indent=2))
    elif args.cmd == "reset":
        paths = {"favourites": (cfg.state_path, cfg.journal_path),
                 "value": (cfg.value_state_path, cfg.value_journal_path),
                 "stocks": (cfg.stocks_state_path, cfg.stocks_journal_path)}[args.pot]
        for path in paths:
            if os.path.exists(path):
                os.remove(path)
        print(f"Reset the {args.pot} pot. Next run starts with £{cfg.starting_bankroll:.2f}.")


if __name__ == "__main__":
    main()
