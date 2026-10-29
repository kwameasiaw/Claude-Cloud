# predbot: Polymarket paper-trading bot

A **paper-money** trading bot for [Polymarket](https://polymarket.com) prediction markets.
It reads live public prices (no account, no API key, no real money) and simulates
trades against the real order book.

## Quick start

Needs Python 3.10+ and nothing else (standard library only).

```bash
python -m predbot scan          # look at today's opportunities, no trading
python -m predbot run           # one cycle: manage positions, maybe open new ones
python -m predbot loop --minutes 15   # keep running every 15 minutes
python -m predbot report        # bankroll, win rate, P&L, open positions
python -m predbot reset         # wipe paper state and start again at £100
python -m unittest -v           # tests
```

State is kept in `paper_state.json`; every closed trade is appended to `trade_journal.csv`.

## The rules it follows

| Rule | Setting |
|---|---|
| Starting pot | £100 paper |
| Size per trade | 10% of current equity (≈ £10 at the start) |
| Max open trades | 5, so at least half the pot is always in cash |
| Markets traded | binary, ≥ $10k liquidity, ≥ $5k traded in 24h, spread ≤ 2c, closes in 1–30 days |
| Entry | buy the favourite only when priced 60–82c, not falling (≤ 3c drop today, ≤ 5c this week), and the model's fair value beats the price paid |
| Correlation | one trade per event at most |
| Fill | walks the real order book; skips if the stake would move the price by more than 1c |
| Stop-loss | sell if the bid falls 20% below the entry price (e.g. 70c → 56c) |
| Take-profit | sell once the bid reaches 95c |
| Otherwise | hold to resolution (pays £1 per share if right, £0 if wrong) |

All of these live in `predbot/config.py`.

### Why favourites priced 60–82c?

If a market is fairly priced, a contract bought at 70c wins about 70% of the time.
So this price band is what gives the 60–70%+ win rate you asked for. The edge
the bot is betting on is the **favourite-longshot bias**: on betting and prediction
markets, favourites have historically resolved slightly *more* often than their
price implies. The bot only buys when that small bias, plus a steady (not falling)
price trend, is still worth more than the spread.

## Read this before trusting it

- **Win rate is not profit.** Buying at 75c and winning 75% of the time breaks
  even. A win only pays about 25–40% of the stake, and a loss held to resolution
  costs all of it. So `report` shows a **break-even win rate** (the average entry
  price) next to the real one. The strategy only has an edge if the real win rate
  is consistently *above* the break-even one.
- **The edge is small and unproven.** The favourite-longshot bias is real
  but worth about 1–3c. That is exactly why this runs on paper first. Judge it after
  **at least 30–50 closed trades**, not after a good or bad week.
- **Stops can be jumped.** Prediction-market prices can gap straight from 70c to 5c on
  news. The stop sells at whatever the bid is when the bot next checks, which can
  be far below the stop price.
- **Paper fills are optimistic.** Real trading adds latency, partial fills and other
  people reacting to the same news.
- Polymarket quotes in USD; the paper pot treats each unit as £1.
- Real-money access to Polymarket depends on where you live. Check the rules in your
  country (including the UK) before ever going live.
