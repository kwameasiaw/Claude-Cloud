"""Builds report.html: every pot's won, lost and open trades in tables, one page."""
import json
import os
from datetime import datetime, timezone
from html import escape

from .config import Config

POTS = [("Favourites", "state_path", "Buys the favourite at 60–82p"),
        ("Value", "value_state_path", "Buys the underpriced side at 20–80p"),
        ("Stocks", "stocks_state_path", "Buys dips in big US stocks"),
        ("Crypto", "crypto_state_path", "Buys dips in large coins")]


WHY = {"stop-loss": "Stop-loss", "take-profit": "Recovered", "resolved WIN": "Won outright",
       "resolved LOSS": "Lost outright", "time-exit": "Time limit"}


def money(v, sign=False):
    s = f"£{abs(v):,.2f}"
    return (("+" if v > 0.004 else "−" if v < -0.004 else "") + s) if sign else s


def price(p, long):
    if not long: return "£1" if p >= 0.999 else f"{p*100:.0f}p"
    return f"${p:,.2f}" if p >= 1 else f"${p:.4f}"


def cls(v): return "pos" if v > 0.004 else "neg" if v < -0.004 else ""


def render_report(cfg: Config) -> str:
    cards, sections, total, total_real = [], [], 0.0, 0.0
    for name, attr, blurb in POTS:
        path = getattr(cfg, attr)
        if not os.path.exists(path):
            continue
        with open(path) as fh:
            d = json.load(fh)
        long = name in ("Stocks", "Crypto")
        pos = d["positions"]; closed = d["closed"]
        open_val = sum(p["shares"] * (p.get("last_bid") or p["entry_price"]) for p in pos)
        equity = d["cash"] + open_val; change = equity - d["starting_bankroll"]
        total += equity
        wins = [t for t in closed if t["pnl"] > 0]; losses = [t for t in closed if t["pnl"] <= 0]
        realised = sum(t["pnl"] for t in closed); total_real += realised
        wr = f"{len(wins)/len(closed)*100:.0f}%" if closed else "—"
        cards.append(f"""<div class="card"><div class="eyebrow">{name}</div>
          <div class="big">{money(equity)}</div><div class="delta {cls(change)}">{money(change, True)} ({change/d['starting_bankroll']*100:+.1f}%)</div>
          <div class="meta"><span><b>{len(wins)}</b> won</span><span><b>{len(losses)}</b> lost</span><span><b>{len(pos)}</b> open</span><span>win rate <b>{wr}</b></span></div></div>""")

        def closed_rows(ts):
            if not ts: return '<tr><td colspan="6" class="empty">None yet</td></tr>'
            return "".join(f"<tr><td>{escape(t['question'])}<div class='sub'>{escape(t['outcome'])} · {t['closed_at'][:10]}</div></td>"
                           f"<td class='r'>{price(t['entry_price'], long)}</td><td class='r'>{price(t['exit_price'], long)}</td>"
                           f"<td class='r'>{money(t['stake'])}</td><td class='r {cls(t['pnl'])}'>{money(t['pnl'], True)}</td>"
                           f"<td>{WHY.get(t['reason'], t['reason'])}</td></tr>"
                           for t in sorted(ts, key=lambda t: t["closed_at"], reverse=True))
        def open_rows():
            if not pos: return '<tr><td colspan="6" class="empty">None open</td></tr>'
            rows = ""
            for p in pos:
                now = p.get("last_bid") or p["entry_price"]; pnl = p["shares"] * now - p["stake"]
                rows += (f"<tr><td>{escape(p['question'])}<div class='sub'>{escape(p['outcome'])} · opened {p['opened_at'][:10]}</div></td>"
                         f"<td class='r'>{price(p['entry_price'], long)}</td><td class='r'>{price(now, long)}</td>"
                         f"<td class='r'>{price(p['stop_price'], long)}</td><td class='r'>{money(p['stake'])}</td>"
                         f"<td class='r {cls(pnl)}'>{money(pnl, True)}</td></tr>")
            return rows
        head_c = "<tr><th>Bet</th><th class='r'>Bought</th><th class='r'>Closed at</th><th class='r'>Stake</th><th class='r'>P&amp;L</th><th>Why</th></tr>"
        head_o = "<tr><th>Bet</th><th class='r'>Bought</th><th class='r'>Now</th><th class='r'>Stop</th><th class='r'>Stake</th><th class='r'>P&amp;L so far</th></tr>"
        sections.append(f"""<section><div class="sechead"><h2>{name}</h2><span class="blurb">{blurb}</span>
          <span class="pill {cls(change)}">{money(equity)} · {money(change, True)}</span></div>
          <h3><span class="dot win"></span>Won <span class="n">{len(wins)}</span></h3><div class="tw"><table>{head_c}{closed_rows(wins)}</table></div>
          <h3><span class="dot loss"></span>Lost <span class="n">{len(losses)}</span></h3><div class="tw"><table>{head_c}{closed_rows(losses)}</table></div>
          <h3><span class="dot open"></span>Still open <span class="n">{len(pos)}</span></h3><div class="tw"><table>{head_o}{open_rows()}</table></div></section>""")

    tc = total - cfg.starting_bankroll * len(cards)
    now = datetime.now(timezone.utc)
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Paper Pot Report</title><style>
    :root{{--bg:#f5f6f8;--panel:#fff;--ink:#15181d;--ink2:#555d6b;--ink3:#8a909c;--rule:#e4e7ec;--pos:#0f8a3c;--neg:#c93838;--acc:#2a6fd6;--wash:#eef2f8}}
    @media (prefers-color-scheme:dark){{:root{{--bg:#111317;--panel:#1a1d23;--ink:#eceef2;--ink2:#b3b9c4;--ink3:#7f8694;--rule:#2b3039;--pos:#3fc06d;--neg:#ef6a6a;--acc:#5b9bf0;--wash:#202631}}}}
    *{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif}}
    .wrap{{max-width:980px;margin:0 auto;padding:32px 16px 64px;display:grid;gap:28px}}
    header{{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:end;gap:12px}}
    h1{{margin:0;font-size:1.7rem;letter-spacing:-.02em}}.stamp{{color:var(--ink3);font-size:.85rem}}
    .hero{{background:var(--panel);border:1px solid var(--rule);border-radius:14px;padding:20px 22px;display:flex;flex-wrap:wrap;gap:8px 32px;align-items:baseline}}
    .hero .big{{font-size:2.6rem}}.hero .lbl{{color:var(--ink2)}}
    .cards{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}}
    @media (max-width:800px){{.cards{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}@media (max-width:460px){{.cards{{grid-template-columns:1fr}}}}
    .card{{background:var(--panel);border:1px solid var(--rule);border-radius:12px;padding:16px;display:grid;gap:4px}}
    .eyebrow{{font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:var(--ink3);font-weight:600}}
    .big{{font-size:1.8rem;font-weight:650;font-variant-numeric:tabular-nums;letter-spacing:-.02em}}
    .delta{{font-weight:600;font-variant-numeric:tabular-nums}}.pos{{color:var(--pos)}}.neg{{color:var(--neg)}}
    .meta{{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:.82rem;color:var(--ink2);margin-top:6px}}.meta b{{color:var(--ink)}}
    section{{background:var(--panel);border:1px solid var(--rule);border-radius:14px;padding:20px 22px;display:grid;gap:10px}}
    .sechead{{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 14px}}h2{{margin:0;font-size:1.25rem}}.blurb{{color:var(--ink2);font-size:.9rem;flex:1}}
    .pill{{font-size:.85rem;font-weight:600;padding:3px 10px;border-radius:999px;background:var(--wash);font-variant-numeric:tabular-nums}}
    h3{{margin:10px 0 0;font-size:.9rem;display:flex;align-items:center;gap:8px}}.n{{color:var(--ink3);font-weight:500}}
    .dot{{width:9px;height:9px;border-radius:50%;display:inline-block}}.dot.win{{background:var(--pos)}}.dot.loss{{background:var(--neg)}}.dot.open{{background:var(--acc)}}
    .tw{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-size:.87rem;table-layout:fixed;min-width:620px}}th:first-child{{width:40%}}
    th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid var(--rule);vertical-align:top}}
    th{{font-size:.7rem;letter-spacing:.06em;text-transform:uppercase;color:var(--ink3);font-weight:600}}
    .r{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}.sub{{color:var(--ink3);font-size:.78rem}}
    .empty{{color:var(--ink3);font-style:italic}}tr:last-child td{{border-bottom:0}}
    .note{{color:var(--ink3);font-size:.82rem}}
    </style></head><body><div class="wrap">
    <header><h1>Paper Pot report</h1><span class="stamp">Practice money only · {now:%d %b %Y, %H:%M} UTC</span></header>
    <div class="hero"><div><div class="lbl">All four pots</div><div class="big">{money(total)}</div></div>
    <div><div class="lbl">vs {money(cfg.starting_bankroll * len(cards))} start</div><div class="big {cls(tc)}">{money(tc, True)}</div></div>
    <div><div class="lbl">Banked from finished trades</div><div class="big {cls(total_real)}">{money(total_real, True)}</div></div></div>
    <div class="cards">{''.join(cards)}</div>
    {''.join(sections)}
    <p class="note">Prediction-market prices are in pence (81p ≈ 81% chance). Stock and coin prices are US dollars; each pot counts £1 as $1. "Recovered" means the bot sold once the price climbed back above its 5-day average.</p>
    </div></body></html>"""
    return html


def write_report(cfg: Config) -> None:
    with open(cfg.report_path, "w", encoding="utf-8") as f:
        f.write(render_report(cfg))
