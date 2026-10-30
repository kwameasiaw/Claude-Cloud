"""Builds dashboard.html: a plain-English, self-contained view of the paper pot."""
import json
import os
from datetime import datetime, timezone
from html import escape

from . import llm
from .agents import postmortem
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
.pots { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 14px; }
@media (max-width: 560px) { .pots { grid-template-columns: minmax(0,1fr); } }
.pot { display: grid; gap: 6px; }
.pot .value { font: 650 2.1rem/1.05 var(--f-body); font-variant-numeric: tabular-nums; letter-spacing: -.02em; }
.pot .facts { font-size: .84rem; }
.part { display: grid; gap: 28px; padding-top: 8px; border-top: 1px solid var(--rule); }
.part > h2 { font-size: 1.45rem; }
.funnel { display: grid; gap: 8px; }
.f-row { display: grid; grid-template-columns: 10.5rem minmax(0,1fr) 3.2rem; gap: 10px; align-items: center; font-size: .9rem; }
.f-row .track { height: 12px; position: relative; }
.f-row .fill { position: absolute; inset: 0 auto 0 0; background: var(--accent); border-radius: 0 4px 4px 0; min-width: 2px; }
.f-row .val { text-align: right; font: 600 .9rem var(--f-data); }
@media (max-width: 560px) { .f-row { grid-template-columns: minmax(0,1fr) 3.2rem; } .f-row .track { grid-column: 1 / -1; grid-row: 2; } }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { font-size: .78rem; font-weight: 600; padding: 2px 10px; border-radius: 999px; border: 1px solid var(--rule); color: var(--ink-2); background: var(--panel); }
.chip.on { background: var(--good-wash); color: var(--ink); border-color: transparent; }
.chip.off { background: var(--track); }
.pm { display: grid; gap: 10px; }
.pm ul { margin: 0; padding-left: 0; list-style: none; display: grid; gap: 6px; }
.pm li { display: grid; grid-template-columns: 6.5rem minmax(0,1fr); gap: 8px; font-size: .88rem; color: var(--ink-2); }
.pm li b { color: var(--ink); font-weight: 600; text-transform: capitalize; }
@media (max-width: 560px) { .pm li { grid-template-columns: minmax(0,1fr); gap: 0; } }
.note { font-size: .88rem; color: var(--ink-2); padding: 10px 12px; border-radius: 8px; background: var(--accent-wash); max-width: 65ch; }
"""

TIP_JS = """
(function(){
  document.querySelectorAll('.chart[data-points]').forEach(function(box){
  var pts = JSON.parse(box.dataset.points), svg = box.querySelector('svg'),
      tip = box.querySelector('.tip'), cross = svg.querySelector('.cross');
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
  });
})();
"""


def _gbp(v: float, sign: bool = False) -> str:
    return f"{'+' if sign and v > 0 else ''}{'-' if v < 0 else ''}&pound;{abs(v):,.2f}"


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
    out.append(f'<line class="cross" x1="0" x2="0" y1="{T}" y2="{base}" stroke="var(--ink-3)" stroke-width="1" style="display:none"/>')
    out.append(f'<rect x="{L}" y="0" width="{W-L-R}" height="{H}" fill="transparent"/>')
    out.append("</svg>")
    data = [{"x": round(x, 1), "y": round(y, 1), "label": f"{t:%d %b %H:%M} UTC  £{v:,.2f}"}
            for (x, y), (t, v) in zip(pts, hist)]
    return (f'<div class="chart" data-points=\'{escape(json.dumps(data))}\'>'
            + "".join(out) + '<div class="tip" hidden></div></div>')


def scorecard(st: dict, noun: str) -> str:
    if not st["trades"]:
        return (f'<div class="verdict wait">No {noun}s have finished yet, so there is no win rate. '
                'Results appear here as each one closes.</div>')
    wr = st["win_rate"] * 100
    be = st["break_even_win_rate"] * 100 if st["break_even_win_rate"] is not None else None
    rows = [(f"{noun.capitalize()}s won so far", wr, "var(--accent)")]
    if be is not None:
        rows.append(("Needed to break even", be, "var(--ink-3)"))
    bars = "".join(
        f'<div class="bar-row"><span>{label}</span><div class="track"><div class="fill" '
        f'style="width:{min(v,100):.1f}%;background:{c}"></div></div><span class="val">{v:.0f}%</span></div>'
        for label, v, c in rows)
    n = st["trades"]
    if n < 30 or be is None:
        verdict = ("wait", f"Only {n} {noun}{'s' if n != 1 else ''} finished. Wait for about 30 before judging; "
                   "a few lucky or unlucky results can swing these numbers a lot.")
    elif wr > be:
        verdict = ("good", f"Winning {wr - be:.0f} points more often than needed. The strategy looks like it has an edge.")
    else:
        verdict = ("bad", f"Winning {be - wr:.0f} points less often than needed. So far the strategy is losing money.")
    return f'<div class="score">{bars}</div><div class="verdict {verdict[0]}">{verdict[1]}</div>'


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


def _track(lo: float, hi: float, stop: float, paid: float, now_p: float, target: float | None,
           fmt, label: str) -> str:
    pct = lambda p: f"{max(0, min(100, (p - lo) / (hi - lo) * 100)):.1f}%"
    win = (f'<div class="zone win" style="width:calc(100% - {pct(target)})"></div>'
           f'<div class="mk" style="left:{pct(target)}"><span>cash out {fmt(target)}</span><i class="tick"></i></div>'
           if target else "")
    return f"""<div class="ptrack" role="img" aria-label="{label}">
    <div class="line"></div>
    <div class="zone stop" style="width:{pct(stop)}"></div>{win}
    <div class="mk" style="left:{pct(stop)}"><span>stop {fmt(stop)}</span><i class="tick"></i></div>
    <div class="mk paid below" style="left:{pct(paid)}"><i class="dot"></i></div>
    <div class="mk now below" style="left:{pct(now_p)}"><i class="dot"></i><span>now {fmt(now_p)}</span></div>
  </div>"""


def bet_card(pos: Position, cfg: Config, now: datetime, lo: float) -> str:
    now_p = pos.last_bid if pos.last_bid is not None else pos.entry_price
    pnl = pos.shares * now_p - pos.stake
    pill = "good" if pnl > 0.005 else "bad" if pnl < -0.005 else ""
    pred = pos.decision.get("prediction", {})
    why = (f'<p class="small">Bot\'s estimate {pred["p_final"]*100:.0f}% vs market {pred["p_market"]*100:.0f}% '
           f'({escape(pred.get("method", ""))}), confidence {pred.get("confidence", 0):.2f}</p>' if pred else "")
    pence = lambda p: f"{p*100:.0f}p"
    return f"""
<article class="panel bet">
  <div class="bet-head">
    <a href="{escape(pos.url)}" target="_blank" rel="noopener">{escape(pos.question)}</a>
    <span class="pill {pill}">{_gbp(pnl, True)} so far</span>
  </div>
  <div class="facts"><span>Bet on <b>{escape(pos.outcome)}</b></span><span>Staked <b>{_gbp(pos.stake)}</b>
    at <b>{pos.entry_price*100:.0f}p</b></span>
    <span>Pays <b>{_gbp(pos.shares)}</b> if right</span><span>{_days_left(pos, now)}</span></div>
  {why}
  {_track(lo, 1.0, pos.stop_price, pos.entry_price, now_p, cfg.take_profit_price, pence,
          f"Price now {now_p*100:.0f}p; paid {pos.entry_price*100:.0f}p; stop-loss {pos.stop_price*100:.0f}p")}
</article>"""


def _usd(p: float) -> str:
    """Dollar price; coins under $1 (e.g. Dogecoin) need more than two decimals."""
    return f"${p:,.2f}" if p >= 1 else f"${p:.4f}"


def stock_card(pos: Position, now: datetime,
               hold: str = "after about 10 trading days", group: str = "Sector") -> str:
    now_p = pos.last_bid if pos.last_bid is not None else pos.entry_price
    pnl = pos.shares * now_p - pos.stake
    pill = "good" if pnl > 0.005 else "bad" if pnl < -0.005 else ""
    lo, hi = pos.stop_price * 0.98, max(pos.entry_price, now_p) * 1.04
    usd = _usd
    opened = _when(pos.opened_at)
    held = f"held {(now - opened).days} day{'s' if (now - opened).days != 1 else ''}" if opened else ""
    return f"""
<article class="panel bet">
  <div class="bet-head">
    <a href="{escape(pos.url)}" target="_blank" rel="noopener">{escape(pos.question)}</a>
    <span class="pill {pill}">{_gbp(pnl, True)} so far</span>
  </div>
  <div class="facts"><span>Bought <b>{_gbp(pos.stake)}</b> at <b>{usd(pos.entry_price)}</b></span>
    <span>{group} <b>{escape(", ".join(pos.tags))}</b></span><span>{held}</span></div>
  <p class="small">{escape("; ".join(pos.decision.get("signal", [])))}. Sells when the price recovers above its
    5-day average, at the stop, or {hold}.</p>
  {_track(lo, hi, pos.stop_price, pos.entry_price, now_p, None, usd,
          f"Price now {usd(now_p)}; paid {usd(pos.entry_price)}; stop-loss {usd(pos.stop_price)}")}
</article>"""


def closed_table(rows: list[tuple[str, object]]) -> str:
    if not rows:
        return '<p class="empty">None yet. Finished trades will be listed here with what they made or lost.</p>'
    why = {"stop-loss": "Sold at stop-loss", "take-profit": "Sold at target", "resolved WIN": "Won",
           "resolved LOSS": "Lost", "time-exit": "Sold on time limit"}
    price = lambda t, v: _usd(v) if t.outcome == "Long" else f"{v*100:.0f}p"
    body = "".join(
        f'<tr><td>{escape(t.question)}<div class="small">{pot} &middot; {escape(t.outcome)} &middot; '
        f'{why.get(t.reason, t.reason)}</div></td><td class="r">{price(t, t.entry_price)}</td>'
        f'<td class="r">{price(t, t.exit_price)}</td><td class="r">{_gbp(t.pnl, True)}</td></tr>'
        for pot, t in sorted(rows, key=lambda r: r[1].closed_at, reverse=True))
    return ('<div class="table-wrap"><table><thead><tr><th>Trade</th><th class="r">Bought</th>'
            f'<th class="r">Sold / paid out</th><th class="r">Profit</th></tr></thead><tbody>{body}</tbody></table></div>')


def pot_card(name: str, pf: Portfolio, cfg: Config, noun: str) -> str:
    st = pf.stats()
    change = st["equity"] - pf.starting_bankroll
    direction = "up" if change > 0.005 else "down" if change < -0.005 else "flat"
    arrow = {"up": "&#9650;", "down": "&#9660;", "flat": "&#9644;"}[direction]
    wr = f"{st['win_rate']*100:.0f}% won" if st["win_rate"] is not None else "none finished yet"
    return f"""<div class="panel pot">
    <span class="eyebrow">{name}</span>
    <span class="value">{_gbp(st['equity'])}</span>
    <span class="delta {direction}">{arrow} {_gbp(change, True)} ({st['return_pct']:+.1f}%) since the start</span>
    <div class="facts"><span><b>{len(pf.positions)}</b> of {cfg.max_open_positions} {noun}s open</span>
      <span><b>{_gbp(st['cash'])}</b> cash</span><span><b>{st['trades']}</b> finished, {wr}</span></div>
  </div>"""


def pipeline(pf: Portfolio, cfg: Config) -> str:
    run = pf.last_run or {}
    meta = {}
    if os.path.exists(cfg.model_meta_path):
        with open(cfg.model_meta_path) as f:
            meta = json.load(f)
    sources = set(run.get("sources", []))
    chip = lambda on, text: f'<span class="chip {"on" if on else "off"}">{text}</span>'
    if meta.get("beats_market"):
        model = chip(True, "XGBoost model: on")
    elif meta:
        model = chip(False, f"XGBoost model: off (didn't beat market prices on {meta.get('markets', 0):,} past markets)")
    else:
        model = chip(False, "XGBoost model: not trained yet")
    chips = "".join([
        chip("news" in sources, "Google News " + ("on" if "news" in sources else "off")),
        chip("bbc" in sources, "BBC " + ("on" if "bbc" in sources else "off")),
        chip("guardian" in sources, "Guardian " + ("on" if "guardian" in sources else "off")),
        chip("x" in sources, "X " + ("on" if "x" in sources else "off")),
        chip(llm.available(), "Claude analysis " + ("on" if llm.available() else "off")),
        model,
    ])
    if run.get("skipped"):
        body = f'<div class="note">Last run: {escape(run["skipped"])}.</div>'
    elif "scanned" in run:
        steps = [("Markets scanned", run.get("scanned", 0)), ("Passed the filters", run.get("passed_filters", 0)),
                 ("In the price range", run.get("candidates", 0)),
                 ("Edge on past data", run.get("shortlisted", 0)), ("Researched", run.get("researched", 0)),
                 ("Cleared prediction", run.get("predicted_fire", 0)), ("Approved by risk", run.get("approved", 0)),
                 ("Bets placed", run.get("traded", 0))]
        top = max(1, steps[0][1])
        body = '<div class="funnel">' + "".join(
            f'<div class="f-row"><span>{label}</span><div class="track"><div class="fill" '
            f'style="width:{v / top * 100:.2f}%"></div></div><span class="val">{v:,}</span></div>'
            for label, v in steps) + "</div>"
        body += (f'<p class="small">{run.get("flagged", 0):,} markets were flagged and skipped for unusual price '
                 'swings or very wide spreads.</p>')
        for ex in run.get("blocked_examples", [])[:3]:
            body += f'<p class="small">Risk blocked: {escape(ex)}</p>'
    else:
        body = '<p class="empty">The pipeline summary appears after the next run.</p>'
    return f'<div class="panel" style="display:grid;gap:14px"><div class="chips">{chips}</div>{body}</div>'


def lessons_panel(cfg: Config) -> str:
    lessons = postmortem.load_lessons(cfg)
    label = {"avoid_tag": "Avoid topic", "caution_category": "Extra caution on",
             "raise_min_edge": "Require a bigger edge", "lower_max_price": "Buy fewer expensive favourites"}
    def nice(key):
        kind, _, value = key.partition(":")
        return label.get(kind, kind) + (f" '{value}'" if value else "")
    active = "".join(f'<span class="chip on">{escape(nice(k))}</span>' for k in lessons.get("active", []))
    pending = "".join(f'<span class="chip">{escape(nice(k))} ({n} of {cfg.lesson_min_repeats})</span>'
                      for k, n in lessons.get("counts", {}).items() if k not in lessons.get("active", []))
    rules = (f'<div class="chips">{active}{pending}</div>' if active or pending else
             '<p class="empty">No lessons yet. A lesson changes the bot only after the same problem shows up in '
             f'{cfg.lesson_min_repeats} separate losses.</p>')
    posts = postmortem.recent(cfg, 5)
    cards = "".join(f"""<article class="panel pm">
    <div class="bet-head"><span><b>{escape(r['question'])}</b></span>
      <span class="pill {'bad' if r['verdict'] == 'process error' else ''}">{escape(r['verdict'])} &middot; {_gbp(r['pnl'], True)}</span></div>
    <ul>{"".join(f"<li><b>{escape(v['area'])}</b><span>{escape(v['finding'])}</span></li>" for v in r['reviews'])}</ul>
  </article>""" for r in posts) or '<p class="empty">No losing trades yet, so no postmortems.</p>'
    return f'<div class="panel" style="display:grid;gap:10px"><span class="eyebrow">Lessons in force</span>{rules}</div>{cards}'


def prediction_section(pf: Portfolio, cfg: Config, title: str, blurb: str, now: datetime) -> str:
    lo = track_floor(pf)
    bets = "".join(bet_card(p, cfg, now, lo) for p in pf.positions) or \
        '<p class="empty">No open bets right now. The bot only bets when a market passes every check.</p>'
    return f"""<section class="part">
    <h2>{title}</h2>
    <p class="muted">{blurb}</p>
    <section>
      <h2>How the bot decided this hour</h2>
      {pipeline(pf, cfg)}
    </section>
    <section>
      <h2>Pot over time</h2>
      <div class="panel">{pot_chart(pf)}</div>
    </section>
    <section>
      <h2>Is it winning often enough?</h2>
      <div class="panel">{scorecard(pf.stats(), "bet")}</div>
    </section>
    <section>
      <h2>Open bets</h2>
      <p class="muted">Each line shows prices from {lo*100:.0f}p to &pound;1. The blue dot is the price now. In the red
        zone the bot sells to limit the loss; in the green zone it sells to lock in the gain.</p>
      <div class="legend"><span><i style="background:var(--bad);opacity:.5"></i>Stop-loss zone</span>
        <span><i style="background:var(--good);opacity:.5"></i>Cash-out zone</span>
        <span><i style="background:var(--accent);border-radius:50%;width:10px;height:10px"></i>Price now</span>
        <span><i style="border:2px solid var(--ink-2);border-radius:50%;width:8px;height:8px"></i>Price paid</span></div>
      <div class="bets">{bets}</div>
    </section>
  </section>"""


def spend_panel(cfg: Config, now: datetime) -> str:
    sp = llm.spend_summary(cfg.llm_usage_path)
    if not sp["calls"]:
        why = ("The key is set; nothing has been spent yet." if llm.available()
               else "No Claude API key is set yet, so nothing has been spent.")
        return f'<div class="panel"><p class="empty">{why}</p></div>'
    used = sp["total"] / cfg.llm_budget_usd * 100
    first = _when(sp["first"]) or now
    days = max(1.0, (now - first).total_seconds() / 86400)
    per_day = sp["week"] / min(7.0, days)
    left = cfg.llm_budget_usd - sp["total"]
    if left <= 0:
        runway = "The budget is used up; top up or the Claude steps will stop working."
    elif per_day > 0:
        runway = f"At the last week's pace (${per_day:.2f} a day) the rest lasts about {left / per_day:.0f} more days."
    else:
        runway = "No spend in the last week."
    names = {"news scoring": "News scoring", "postmortem": "Postmortems"}
    rows = "".join(
        f'<tr><td>{escape(names.get(k, k))}</td><td class="r">{v["calls"]:,}</td><td class="r">${v["cost"]:.2f}</td></tr>'
        for k, v in sorted(sp["by_purpose"].items(), key=lambda kv: -kv[1]["cost"]))
    models = ", ".join(f"{escape(m)} ({v['calls']:,} calls)" for m, v in sp["by_model"].items())
    return f"""<div class="panel" style="display:grid;gap:14px">
    <div class="bar-row"><span>Used of your ${cfg.llm_budget_usd:.0f}</span><div class="track"><div class="fill"
      style="width:{min(used, 100):.1f}%;background:var(--accent)"></div></div><span class="val">${sp['total']:.2f}</span></div>
    <div class="facts"><span>Today <b>${sp['today']:.2f}</b></span><span>Last 7 days <b>${sp['week']:.2f}</b></span>
      <span><b>{sp['calls']:,}</b> calls</span></div>
    <p class="small">{runway} Costs are estimated from token counts at list prices; your Claude Console shows the exact bill.</p>
    <div class="table-wrap"><table><thead><tr><th>Used for</th><th class="r">Calls</th><th class="r">Cost</th></tr></thead>
      <tbody>{rows}</tbody></table></div>
    <p class="small">Models: {models}.</p>
  </div>"""


def render(cfg: Config, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    from .engine import pot_config
    fav_cfg, val_cfg = pot_config(cfg, "favourites"), pot_config(cfg, "value")
    pm = Portfolio.load(fav_cfg.state_path, cfg.starting_bankroll)
    vp = Portfolio.load(val_cfg.state_path, cfg.starting_bankroll)
    sk = Portfolio.load(cfg.stocks_state_path, cfg.starting_bankroll)
    trades = "".join(stock_card(p, now) for p in sk.positions) or \
        '<p class="empty">No open stock trades right now.</p>'
    stock_status = sk.last_run.get("skipped", "")
    cp = Portfolio.load(cfg.crypto_state_path, cfg.starting_bankroll)
    coins = "".join(stock_card(p, now, "after 10 days", "Group") for p in cp.positions) or \
        '<p class="empty">No open crypto trades right now.</p>'
    crypto_status = cp.last_run.get("skipped", "")
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

  <div class="pots">
    {pot_card("Favourites pot", pm, cfg, "bet")}
    {pot_card("Value pot", vp, cfg, "bet")}
    {pot_card("Stocks pot", sk, cfg, "trade")}
    {pot_card("Crypto pot", cp, cfg, "trade")}
  </div>
  <p class="small">Four separate &pound;100 pots, so you can see which approach actually works. Every hour five
    agents run for each prediction-market pot: scan all markets, research the best ones, estimate the real chance,
    check the risk and size the bet, then review any losses.</p>

  {prediction_section(pm, fav_cfg, "Favourites pot",
      f"Buys only the favourite, priced {fav_cfg.min_entry_price*100:.0f}&ndash;{fav_cfg.max_entry_price*100:.0f}p, "
      "aiming for a high win rate. Past data says favourites in this range have been slightly overpriced, so "
      "expect this pot to bet rarely.", now)}

  {prediction_section(vp, val_cfg, "Value pot",
      f"Buys whichever side, priced {val_cfg.min_entry_price*100:.0f}&ndash;{val_cfg.max_entry_price*100:.0f}p, "
      "past data says is underpriced. That is often the outsider, so expect to win less often (around 35&ndash;55%) "
      f"but collect more per win. Its stop-loss is {val_cfg.stop_loss_pct*100:.0f}% below the price paid, wider than "
      "the favourites pot, because cheaper prices swing more.", now)}

  <section class="part">
    <h2>Stocks</h2>
    {f'<div class="note">{escape(stock_status)}.</div>' if stock_status else ''}
    <p class="muted">The stocks pot buys sharp short dips in the S&amp;P 500 and Nasdaq index funds (SPY, QQQ) and the
      biggest US companies, but only while each is in a long-term uptrend. Each trade risks about 1.5% of the pot
      if the stop is hit, and never more than 10% of the pot goes into one trade. Share prices are in US dollars;
      the pot counts &pound;1 as $1.</p>
    <section>
      <h2>Pot over time</h2>
      <div class="panel">{pot_chart(sk)}</div>
    </section>
    <section>
      <h2>Is it winning often enough?</h2>
      <p class="muted">For stocks, break-even depends on how big the wins are compared with the losses. If wins are
        half the size of losses, the bot must win two trades in three.</p>
      <div class="panel">{scorecard(sk.stats(), "trade")}</div>
    </section>
    <section>
      <h2>Open trades</h2>
      <div class="bets">{trades}</div>
    </section>
  </section>

  <section class="part">
    <h2>Crypto</h2>
    {f'<div class="note">{escape(crypto_status)}.</div>' if crypto_status else ''}
    <p class="muted">The crypto pot uses the same rule as the stocks pot on the biggest coins (Bitcoin, Ether, Solana
      and others): buy a sharp two-day dip, but only while the coin is above its 200-day average. Coins trade every
      day and swing about three times as much as big stocks, so stops sit 5&ndash;15% below the price paid and
      trades last at most 10 days. It holds at most two of Bitcoin and Ether, and at most two smaller coins, because
      coins tend to rise and fall together. Prices are in US dollars; the pot counts &pound;1 as $1.</p>
    <section>
      <h2>Pot over time</h2>
      <div class="panel">{pot_chart(cp)}</div>
    </section>
    <section>
      <h2>Is it winning often enough?</h2>
      <div class="panel">{scorecard(cp.stats(), "trade")}</div>
    </section>
    <section>
      <h2>Open trades</h2>
      <div class="bets">{coins}</div>
    </section>
  </section>

  <section class="part">
    <h2>Claude API spend</h2>
    <p class="muted">News scoring runs on Claude Haiku, the cheapest model, because it happens often and is a simple
      job. Postmortems run on Claude Opus, the stronger model, because they are rarer and need more judgement.</p>
    {spend_panel(cfg, now)}
  </section>

  <section class="part">
    <h2>Lessons from losses</h2>
    <p class="muted">After every losing trade, five reviewers each check one step (scan, research, prediction, risk,
      execution) and decide whether it was bad luck or a mistake. Some losses are expected even when everything is
      done right, so a lesson only changes the bot once the same mistake shows up {cfg.lesson_min_repeats} times,
      and lessons can only make it more careful.</p>
    {lessons_panel(cfg)}
  </section>

  <section>
    <h2>Finished trades</h2>
    <div class="panel">{closed_table([("Favourites pot", t) for t in pm.closed] + [("Value pot", t) for t in vp.closed]
                                     + [("Stocks pot", t) for t in sk.closed]
                                     + [("Crypto pot", t) for t in cp.closed])}</div>
  </section>

  <section>
    <h2>Words you'll see</h2>
    <div class="panel"><dl>
      <dt>Price = chance</dt><dd>A prediction-market share pays &pound;1 if the event happens and nothing if not.
        A price of 80p means the market thinks there's about an 80% chance.</dd>
      <dt>Edge</dt><dd>How much better the bot's estimate is than the price, after fees. An estimate of 84% on an
        81p bet is a 3p edge.</dd>
      <dt>Kelly sizing</dt><dd>A formula that sets the bet size from the edge and the pot. The bot uses a quarter of
        what Kelly suggests, and never more than 10% of the pot, so small edges get small bets.</dd>
      <dt>Stop-loss</dt><dd>A safety exit: sell if the price falls a set amount below what was paid. Big news can make
        prices jump past it.</dd>
      <dt>Dip in an uptrend</dt><dd>A stock or coin that has risen over the past 200 days but fell sharply over the last two.
        These often bounce back within days; sometimes they keep falling, which is what the stop is for.</dd>
      <dt>Break-even win rate</dt><dd>How often trades must win just to not lose money. Beating it is the real goal;
        a high win rate alone isn't enough.</dd>
      <dt>Paper money</dt><dd>Pretend money. Prices are real, but no real money is bought or sold.</dd>
    </dl></div>
  </section>
</div>
<script>{TIP_JS}</script>
"""


def write_dashboard(cfg: Config) -> None:
    with open(cfg.dashboard_path, "w", encoding="utf-8") as f:
        f.write(render(cfg))
