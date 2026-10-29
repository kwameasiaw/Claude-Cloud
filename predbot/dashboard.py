"""Builds dashboard.html: a plain-English, self-contained view of the paper pot."""
import json
from datetime import datetime, timezone
from html import escape

from .config import Config
from .portfolio import Portfolio, Position

CSS = """
/* Layout: one reading column; summary first, then the pot chart, scorecard,
   each open bet drawn as a price track, finished bets, and a glossary. */
:root {
  --bg: #f6f7f9; --panel: #ffffff; --ink: #14171c; --ink-2: #4c5361; --ink-3: #7a8191;
  --rule: #e3e6ec; --accent: #2a78d6; --accent-wash: rgba(42,120,214,.10);
  --good: #0ca30c; --bad: #d03b3b; --bad-wash: rgba(208,59,59,.10); --good-wash: rgba(12,163,12,.12);
  --track: #e9ecf1;
  --f-display: "Bricolage Grotesque", "IBM Plex Sans", system-ui, sans-serif;
  --f-body: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --f-data: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #121418; --panel: #1a1d22; --ink: #eef0f3; --ink-2: #b9bfca; --ink-3: #8a91a0;
  --rule: #2b3038; --accent: #3987e5; --accent-wash: rgba(57,135,229,.16);
  --bad-wash: rgba(208,59,59,.20); --good-wash: rgba(12,163,12,.20); --track: #262a32;
  color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #121418; --panel: #1a1d22; --ink: #eef0f3; --ink-2: #b9bfca; --ink-3: #8a91a0;
  --rule: #2b3038; --accent: #3987e5; --accent-wash: rgba(57,135,229,.16);
  --bad-wash: rgba(208,59,59,.20); --good-wash: rgba(12,163,12,.20); --track: #262a32;
  color-scheme: dark; }
body { background: var(--bg); color: var(--ink); font: 15px/1.55 var(--f-body); }
.wrap { max-width: 760px; margin: 0 auto; display: grid; gap: 28px;
  padding-block: 28px 56px;
  padding-left: max(16px, env(safe-area-inset-left, 0px));
  padding-right: max(16px, env(safe-area-inset-right, 0px)); }
h1, h2 { font-family: var(--f-display); text-wrap: balance; margin: 0; letter-spacing: -.01em; }
h1 { font-size: 1.5rem; font-weight: 700; }
h2 { font-size: 1.2rem; font-weight: 650; }
p { margin: 0; max-width: 65ch; }
.muted { color: var(--ink-2); }
.small { font-size: .85rem; color: var(--ink-3); }
.num { font-family: var(--f-data); font-variant-numeric: tabular-nums; }
.eyebrow { font-size: .72rem; letter-spacing: .08em; text-transform: uppercase; color: var(--ink-3); font-weight: 600; }
header { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 6px 16px; }
.paper { font-size: .78rem; font-weight: 600; color: var(--ink-2); border: 1px solid var(--rule);
  border-radius: 999px; padding: 2px 10px; background: var(--panel); }
section { display: grid; gap: 14px; min-width: 0; }
.panel { background: var(--panel); border: 1px solid var(--rule); border-radius: 12px; padding: 18px; min-width: 0; }
.hero { display: grid; gap: 4px; }
.hero .value { font: 650 3.2rem/1.05 var(--f-body); font-variant-numeric: tabular-nums; letter-spacing: -.02em; }
.delta { font-weight: 600; font-size: 1rem; }
.delta.up { color: var(--good); } .delta.down { color: var(--bad); } .delta.flat { color: var(--ink-2); }
.tiles { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 1px; background: var(--rule);
  border: 1px solid var(--rule); border-radius: 12px; overflow: hidden; }
.tile { background: var(--panel); padding: 12px 14px; display: grid; gap: 2px; }
.tile b { font: 600 1.15rem var(--f-data); font-variant-numeric: tabular-nums; }
@media (max-width: 560px) { .tiles { grid-template-columns: repeat(2, minmax(0,1fr)); } .hero .value { font-size: 2.6rem; } }
.chart { position: relative; }
.chart svg { display: block; width: 100%; height: auto; overflow: visible; }
.chart text { font: 11px var(--f-data); fill: var(--ink-3); }
@media (max-width: 560px) { .chart text { font-size: 17px; } }
.tip { position: absolute; pointer-events: none; background: var(--ink); color: var(--bg); font: 12px/1.4 var(--f-data);
  padding: 6px 8px; border-radius: 6px; white-space: nowrap; transform: translate(-50%, -110%); }
.score { display: grid; gap: 12px; }
.bar-row { display: grid; grid-template-columns: 11.5rem minmax(0,1fr) 3.5rem; gap: 10px; align-items: center; }
.bar-row .track { height: 14px; background: var(--track); border-radius: 0 4px 4px 0; position: relative; }
.bar-row .fill { position: absolute; inset: 0 auto 0 0; border-radius: 0 4px 4px 0; }
.bar-row .val { text-align: right; font: 600 .95rem var(--f-data); }
@media (max-width: 560px) { .bar-row { grid-template-columns: minmax(0,1fr) 3.5rem; } .bar-row .track { grid-column: 1 / -1; grid-row: 2; } }
.verdict { padding: 10px 12px; border-radius: 8px; font-size: .92rem; }
.verdict.good { background: var(--good-wash); } .verdict.bad { background: var(--bad-wash); }
.verdict.wait { background: var(--accent-wash); }
.bets { display: grid; gap: 14px; }
.bet { display: grid; gap: 12px; }
.bet-head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 4px 12px; }
.bet-head a { color: var(--ink); text-decoration: none; font-weight: 600; }
.bet-head a:hover, .bet-head a:focus-visible { text-decoration: underline; }
.pill { display: inline-block; font-size: .78rem; font-weight: 600; padding: 1px 8px; border-radius: 999px;
  background: var(--accent-wash); color: var(--ink); }
.pill.good { background: var(--good-wash); } .pill.bad { background: var(--bad-wash); }
.ptrack { position: relative; height: 62px; margin: 0 28px; }
.ptrack .line { position: absolute; left: 0; right: 0; top: 22px; height: 8px; background: var(--track); border-radius: 4px; }
.ptrack .zone { position: absolute; top: 22px; height: 8px; }
.ptrack .zone.stop { left: 0; background: var(--bad); opacity: .35; border-radius: 4px 0 0 4px; }
.ptrack .zone.win { right: 0; background: var(--good); opacity: .35; border-radius: 0 4px 4px 0; }
.mk { position: absolute; top: 0; transform: translateX(-50%); display: grid; justify-items: center; gap: 2px;
  font: 600 .72rem var(--f-data); color: var(--ink-2); white-space: nowrap; }
.mk.below { top: 19px; }
.mk.paid { top: 20px; }
.mk .tick { width: 2px; height: 16px; background: var(--ink-3); }
.mk.now .dot { width: 14px; height: 14px; border-radius: 50%; background: var(--accent);
  box-shadow: 0 0 0 2px var(--panel); margin-top: 1px; }
.mk.paid .dot { width: 12px; height: 12px; border-radius: 50%; border: 2px solid var(--ink-2); background: var(--panel); }
.facts { display: flex; flex-wrap: wrap; gap: 4px 18px; font-size: .88rem; color: var(--ink-2); }
.facts b { color: var(--ink); font-family: var(--f-data); font-weight: 600; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: .82rem; color: var(--ink-2); }
.legend i { display: inline-block; width: 12px; height: 8px; border-radius: 2px; margin-right: 6px; vertical-align: middle; }
.table-wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: .88rem; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--rule); vertical-align: top; }
th { font-size: .72rem; letter-spacing: .06em; text-transform: uppercase; color: var(--ink-3); font-weight: 600; }
td.r, th.r { text-align: right; font-family: var(--f-data); font-variant-numeric: tabular-nums; white-space: nowrap; }
dl { display: grid; gap: 12px; margin: 0; }
dt { font-weight: 650; } dd { margin: 2px 0 0; color: var(--ink-2); max-width: 65ch; }
.empty { color: var(--ink-2); font-size: .92rem; }
"""

TIP_JS = """
(function(){
  var box = document.getElementById('pot-chart'); if (!box) return;
  var pts = JSON.parse(box.dataset.points), svg = box.querySelector('svg'),
      tip = box.querySelector('.tip'), cross = svg.querySelector('#cross');
  function show(e){
    var r = svg.getBoundingClientRect(), vb = svg.viewBox.baseVal,
        x = (e.clientX - r.left) * vb.width / r.width, best = pts[0];
    pts.forEach(function(p){ if (Math.abs(p.x - x) < Math.abs(best.x - x)) best = p; });
    cross.setAttribute('x1', best.x); cross.setAttribute('x2', best.x); cross.style.display = '';
    tip.hidden = false; tip.textContent = best.label;
    tip.style.left = (best.x * r.width / vb.width) + 'px'; tip.style.top = (best.y * r.height / vb.height) + 'px';
  }
  svg.addEventListener('pointermove', show);
  svg.addEventListener('pointerleave', function(){ tip.hidden = true; cross.style.display = 'none'; });
})();
"""


def _gbp(v: float, sign: bool = False) -> str:
    s = f"{'+' if sign and v > 0 else ''}{'-' if v < 0 else ''}&pound;{abs(v):,.2f}"
    return s


def _when(iso: str) -> datetime | None:
    try:
        return datetime.fromisoformat(iso).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _nice_step(span: float) -> float:
    for step in (0.5, 1, 2, 5, 10, 20, 50, 100):
        if span / step <= 5:
            return step
    return 200


def pot_chart(pf: Portfolio) -> str:
    hist = [(t, h["equity"]) for h in pf.history if (t := _when(h["t"]))]
    if len(hist) < 2:
        return ('<p class="empty">The chart fills in after the bot has run a couple of times. '
                'It checks every hour.</p>')
    W, H, L, R, T, B = 560, 220, 52, 16, 14, 30
    vals = [v for _, v in hist] + [pf.starting_bankroll]
    lo, hi = min(vals), max(vals)
    step = _nice_step(max(hi - lo, 1))
    lo = (lo // step) * step
    hi = (hi // step + 1) * step
    t0, t1 = hist[0][0].timestamp(), hist[-1][0].timestamp()
    sx = lambda t: L + (t.timestamp() - t0) / max(t1 - t0, 1) * (W - L - R)
    sy = lambda v: T + (hi - v) / (hi - lo) * (H - T - B)

    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Pot value over time, '
           f'from {_gbp(hist[0][1])} to {_gbp(hist[-1][1])}">']
    v = lo
    while v <= hi + 1e-9:
        y = sy(v)
        out.append(f'<line x1="{L}" x2="{W-R}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--rule)" stroke-width="1"/>'
                   f'<text x="{L-8}" y="{y+4:.1f}" text-anchor="end">&#163;{v:g}</text>')
        v += step
    y100 = sy(pf.starting_bankroll)
    out.append(f'<line x1="{L}" x2="{W-R}" y1="{y100:.1f}" y2="{y100:.1f}" stroke="var(--ink-3)" stroke-width="1"/>'
               f'<text x="{W-R}" y="{y100-6:.1f}" text-anchor="end">started with &#163;{pf.starting_bankroll:g}</text>')
    for t in (hist[0][0], hist[-1][0]):
        anchor = "start" if t == hist[0][0] else "end"
        out.append(f'<text x="{sx(t):.1f}" y="{H-8}" text-anchor="{anchor}">{t:%d %b %H:%M}</text>')
    pts = [(sx(t), sy(v)) for t, v in hist]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    base = H - B
    out.append(f'<polygon points="{pts[0][0]:.1f},{base} {line} {pts[-1][0]:.1f},{base}" fill="var(--accent-wash)"/>')
    out.append(f'<polyline points="{line}" fill="none" stroke="var(--accent)" stroke-width="2" '
               'stroke-linejoin="round" stroke-linecap="round"/>')
    ex, ey = pts[-1]
    out.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="5" fill="var(--accent)" stroke="var(--panel)" stroke-width="2"/>')
    out.append(f'<line id="cross" x1="0" x2="0" y1="{T}" y2="{base}" stroke="var(--ink-3)" stroke-width="1" style="display:none"/>')
    out.append(f'<rect x="{L}" y="0" width="{W-L-R}" height="{H}" fill="transparent"/>')
    out.append("</svg>")
    data = [{"x": round(x, 1), "y": round(y, 1), "label": f"{t:%d %b %H:%M} UTC  £{v:,.2f}"}
            for (x, y), (t, v) in zip(pts, hist)]
    return (f'<div class="chart" id="pot-chart" data-points=\'{escape(json.dumps(data))}\'>'
            + "".join(out) + '<div class="tip" hidden></div></div>')


def scorecard(pf: Portfolio, st: dict) -> str:
    if not st["trades"]:
        return ('<div class="verdict wait">No bets have finished yet, so there is no win rate. '
                'Results appear here as each bet settles or hits its stop-loss or cash-out price.</div>')
    wr, be = st["win_rate"] * 100, st["expected_win_rate"] * 100
    rows = [("Bets won so far", wr, "var(--accent)"), ("Needed to break even", be, "var(--ink-3)")]
    bars = "".join(
        f'<div class="bar-row"><span>{label}</span><div class="track"><div class="fill" '
        f'style="width:{min(v,100):.1f}%;background:{c}"></div></div><span class="val">{v:.0f}%</span></div>'
        for label, v, c in rows)
    n = st["trades"]
    if n < 30:
        verdict = ("wait", f"Only {n} bet{'s' if n != 1 else ''} finished. Wait for about 30 before judging; "
                   "a few lucky or unlucky results can swing these numbers a lot.")
    elif wr > be:
        verdict = ("good", f"Winning {wr - be:.0f} points more often than needed. The strategy looks like it has an edge.")
    else:
        verdict = ("bad", f"Winning {be - wr:.0f} points less often than needed. So far the strategy is losing money.")
    return (f'<div class="score">{bars}</div>'
            f'<div class="verdict {verdict[0]}">{verdict[1]}</div>')


def _days_left(pos: Position, now: datetime) -> str:
    end = _when(pos.closes_at)
    if not end:
        return "settle date unknown"
    days = (end - now).total_seconds() / 86400
    if days < 1:
        return "settles within a day"
    return f"settles in about {days:.0f} day{'s' if round(days) != 1 else ''}"


def track_floor(pf: Portfolio) -> float:
    """Lowest price drawn on the bet tracks: a bit under the lowest stop or price, in 10p steps."""
    lows = [min(p.stop_price, p.last_bid if p.last_bid is not None else p.entry_price) for p in pf.positions]
    return max(0.0, min([0.5] + [int((v - 0.05) * 10) / 10 for v in lows]))


def bet_card(pos: Position, cfg: Config, now: datetime, lo: float) -> str:
    now_p = pos.last_bid if pos.last_bid is not None else pos.entry_price
    pnl = pos.shares * now_p - pos.stake
    pct = lambda p: f"{max(0, min(100, (p - lo) / (1 - lo) * 100)):.1f}%"
    pill = "good" if pnl > 0.005 else "bad" if pnl < -0.005 else ""
    return f"""
<article class="panel bet">
  <div class="bet-head">
    <a href="{escape(pos.url)}" target="_blank" rel="noopener">{escape(pos.question)}</a>
    <span class="pill {pill}">{_gbp(pnl, True)} so far</span>
  </div>
  <div class="facts"><span>Bet on <b>{escape(pos.outcome)}</b></span><span>Staked <b>{_gbp(pos.stake)}</b>
    at <b>{pos.entry_price*100:.0f}p</b></span>
    <span>Pays <b>{_gbp(pos.shares)}</b> if right</span><span>{_days_left(pos, now)}</span></div>
  <div class="ptrack" role="img" aria-label="Price now {now_p*100:.0f}p; paid {pos.entry_price*100:.0f}p; stop-loss {pos.stop_price*100:.0f}p; cash out at {cfg.take_profit_price*100:.0f}p">
    <div class="line"></div>
    <div class="zone stop" style="width:{pct(pos.stop_price)}"></div>
    <div class="zone win" style="width:calc(100% - {pct(cfg.take_profit_price)})"></div>
    <div class="mk" style="left:{pct(pos.stop_price)}"><span>stop {pos.stop_price*100:.0f}p</span><i class="tick"></i></div>
    <div class="mk" style="left:{pct(cfg.take_profit_price)}"><span>cash out {cfg.take_profit_price*100:.0f}p</span><i class="tick"></i></div>
    <div class="mk paid below" style="left:{pct(pos.entry_price)}"><i class="dot"></i></div>
    <div class="mk now below" style="left:{pct(now_p)}"><i class="dot"></i><span>now {now_p*100:.0f}p</span></div>
  </div>
</article>"""


def closed_table(pf: Portfolio) -> str:
    if not pf.closed:
        return '<p class="empty">None yet. Finished bets will be listed here with what they made or lost.</p>'
    why = {"stop-loss": "Sold at stop-loss", "take-profit": "Cashed out early",
           "resolved WIN": "Won", "resolved LOSS": "Lost", "time-exit": "Sold before close"}
    rows = "".join(
        f'<tr><td>{escape(t.question)}<div class="small">{escape(t.outcome)} &middot; {why.get(t.reason, t.reason)}</div></td>'
        f'<td class="r">{t.entry_price*100:.0f}p</td><td class="r">{t.exit_price*100:.0f}p</td>'
        f'<td class="r">{_gbp(t.pnl, True)}</td></tr>'
        for t in reversed(pf.closed))
    return ('<div class="table-wrap"><table><thead><tr><th>Bet</th><th class="r">Paid</th>'
            f'<th class="r">Sold / paid out</th><th class="r">Profit</th></tr></thead><tbody>{rows}</tbody></table></div>')


def render(pf: Portfolio, cfg: Config, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    st = pf.stats()
    eq, change = st["equity"], st["equity"] - pf.starting_bankroll
    direction = "up" if change > 0.005 else "down" if change < -0.005 else "flat"
    arrow = {"up": "&#9650;", "down": "&#9660;", "flat": "&#9644;"}[direction]
    in_bets = sum(p.stake for p in pf.positions)
    lo = track_floor(pf)
    bets = "".join(bet_card(p, cfg, now, lo) for p in pf.positions) or \
        '<p class="empty">No open bets right now. The bot only bets when a market passes every check.</p>'
    return f"""<title>Paper Pot</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,700&family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;600;650&display=swap">
<style>{CSS}</style>
<div class="wrap">
  <header>
    <h1>Paper Pot</h1>
    <span class="paper">Practice money only &middot; updated {now:%d %b %Y, %H:%M} UTC</span>
  </header>

  <section class="hero" aria-label="Pot value">
    <span class="eyebrow">What your &pound;{pf.starting_bankroll:g} is worth now</span>
    <span class="value">{_gbp(eq)}</span>
    <span class="delta {direction}">{arrow} {_gbp(change, True)} ({st['return_pct']:+.1f}%) since the start</span>
  </section>

  <div class="tiles">
    <div class="tile"><span class="small">Cash not in bets</span><b>{_gbp(st['cash'])}</b></div>
    <div class="tile"><span class="small">Money in open bets</span><b>{_gbp(in_bets)}</b></div>
    <div class="tile"><span class="small">Open bets</span><b>{len(pf.positions)} of {cfg.max_open_positions}</b></div>
    <div class="tile"><span class="small">Finished bets</span><b>{st['trades']}</b></div>
  </div>

  <section>
    <h2>Your pot over time</h2>
    <p class="muted">Open bets are valued at what they could be sold for right now. A small dip right after
      buying is normal: you buy at the asking price and value at the lower selling price.</p>
    <div class="panel">{pot_chart(pf)}</div>
  </section>

  <section>
    <h2>Is it winning often enough?</h2>
    <p class="muted">A bet bought at 80p pays &pound;1 if it wins, so it has to win at least 80% of the time
      to break even. The grey bar is that break-even level for the bets made so far.</p>
    <div class="panel">{scorecard(pf, st)}</div>
  </section>

  <section>
    <h2>Open bets</h2>
    <p class="muted">Each line shows prices from {lo*100:.0f}p to &pound;1. The blue dot is today's price. If it slides into the red
      zone the bot sells to limit the loss; in the green zone it sells to lock in the gain. Otherwise it waits for the result.</p>
    <div class="legend"><span><i style="background:var(--bad);opacity:.5"></i>Stop-loss zone</span>
      <span><i style="background:var(--good);opacity:.5"></i>Cash-out zone</span>
      <span><i style="background:var(--accent);border-radius:50%;width:10px;height:10px"></i>Price now</span>
      <span><i style="border:2px solid var(--ink-2);border-radius:50%;width:8px;height:8px"></i>Price paid</span></div>
    <div class="bets">{bets}</div>
  </section>

  <section>
    <h2>Finished bets</h2>
    <div class="panel">{closed_table(pf)}</div>
  </section>

  <section>
    <h2>Words you'll see</h2>
    <div class="panel"><dl>
      <dt>Price = chance</dt><dd>A share pays &pound;1 if the event happens and nothing if not. A price of 80p
        means the market thinks there's about an 80% chance.</dd>
      <dt>Stop-loss</dt><dd>A safety exit. If the price falls 20% below what was paid, the bot sells and takes
        a small loss rather than risk losing the whole stake. Big news can make prices jump past it.</dd>
      <dt>Cash out</dt><dd>Once a bet reaches 95p the bot sells, locking in most of the win without waiting
        for the result.</dd>
      <dt>Break-even win rate</dt><dd>How often the bets must win just to not lose money. It equals the
        average price paid. Beating it is the real goal; a high win rate alone isn't enough.</dd>
      <dt>Paper money</dt><dd>Pretend money. Prices and order books are real, but no real money is bought or sold.</dd>
    </dl></div>
  </section>
  <p class="small">Each bet is 10% of the pot, at most {cfg.max_open_positions} at once and at most
    {cfg.max_per_theme} on the same topic. Prices come from Polymarket.</p>
</div>
<script>{TIP_JS}</script>
"""


def write_dashboard(pf: Portfolio, cfg: Config) -> None:
    with open(cfg.dashboard_path, "w", encoding="utf-8") as f:
        f.write(render(pf, cfg))
