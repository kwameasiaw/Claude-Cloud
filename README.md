# Paper Pot: Polymarket + US stocks paper-trading bot

Three separate **£100 paper-money pots**, run every hour, so the approaches can be compared:

* **Favourites pot** (Polymarket): buys only the favourite at 60-82p, 20% stop-loss.
* **Value pot** (Polymarket): buys whichever side at 20-80p the calibration data says is
  underpriced (often the outsider), 35% stop-loss. Both use the five-agent pipeline below.
* **Stocks** (SPY, QQQ and ~25 of the largest US companies via Alpaca's free data):
  buys sharp two-day dips in stocks above their 200-day average, sells on recovery,
  at the stop, or after ~10 trading days. Market hours only.

No real money moves. Fills are simulated against live order books and quotes.
`dashboard.html` is rebuilt after each run for a plain-English view.

## The prediction-market pipeline

| Step | Agent | What it does |
|---|---|---|
| 1 | Scan (`agents/scan.py`) | Filters ~1,000 open markets by liquidity, volume, spread and time to close; flags and skips 10c+ daily swings and very wide spreads |
| 2 | Research (`agents/research.py`) | Fetches Google News, BBC and Guardian feeds (plus Reddit and X if configured) in parallel; Claude scores whether the coverage supports the price |
| 3 | Prediction (`agents/predict.py`) | XGBoost model (only if it beat the market on held-out markets) or an empirical calibration table, nudged by Claude by at most 5c; fires only above the edge and confidence bars |
| 4 | Risk (`agents/risk.py`) | Quarter-Kelly sizing, 10% cap, max 5 open, max 2 per topic, drawdown and daily-loss halts, then a paper fill walked through the real order book |
| 5 | Postmortem (`agents/postmortem.py`) | Five reviewers (scan, research, prediction, risk, execution) review every loss; a rule changes behaviour only after 3 separate losses suggest it, and only toward more caution |

## What the data says (read this)

`python -m predbot train` pulls ~4,000 resolved markets. On the ~1,000 usable ones:

* The XGBoost model did **not** beat the market's own prices on the newest 20% of markets,
  so it stays switched off.
* Favourites priced 60-82p won **64%** of the time against an average price of **70%**
  (573 markets, 95% range -9 to -1.5 points). Underdogs at 18-40p won about 6 points
  *more* often than their price. In other words, favourites have been slightly
  **over**priced, so the favourites pot mostly sits out and the value pot tests the reverse.

## Setup

```bash
pip install -r requirements.txt
python -m predbot run           # one cycle for all three pots + dashboard
python -m predbot report        # all three pots in the terminal
python -m predbot scan          # Polymarket candidates, no trading
python -m predbot train         # retrain the model and calibration table
python -m unittest -v           # tests
```

Optional keys (environment variables) and the hosts each needs allowed:

| Feature | Variables | Hosts |
|---|---|---|
| Stocks pot | `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY` (free Alpaca paper account) | `paper-api.alpaca.markets`, `data.alpaca.markets` |
| Claude analysis + postmortems | `ANTHROPIC_API_KEY` (news scoring on Claude Haiku 5.5, postmortems on Claude Opus 5.5; every call's cost is logged to `llm_usage.jsonl` and shown on the dashboard) | `api.anthropic.com` |
| News research | none | `news.google.com` |
| BBC News research | none | `feeds.bbci.co.uk` |
| Guardian research | none | `www.theguardian.com` |
| Reddit research | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` (free "script" app) | `www.reddit.com`, `oauth.reddit.com` |
| X research | `X_BEARER_TOKEN` (paid X API plan) | `api.x.com` |

Without a key, that part is skipped and the dashboard shows it as off.

## Caveats

* Win rate is not profit; the dashboard shows the break-even win rate beside it.
* Stops can be jumped: prices can gap past them between hourly checks.
* Polymarket quotes USD and US stocks trade in USD; both pots count £1 as $1.
* Real-money trading is deliberately not built in. Polymarket and US brokers have their
  own rules on who can trade from where; check them before ever going live.
