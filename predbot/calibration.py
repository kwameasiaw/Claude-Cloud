"""Empirical calibration: how often did outcomes priced around p actually win?

Built from resolved Polymarket markets, one snapshot per market per price bucket
(so busy markets don't count many times). Each bucket's win rate is shrunk toward
its average price in proportion to how little data it has, so thin buckets stay
close to "the market is right".
"""
import json
import os

BUCKET = 0.05
SHRINK = 60          # pseudo-markets of "market is right" mixed into every bucket


def build(groups: list[list], horizon_days: float = 5.0) -> dict:
    buckets: dict[str, dict] = {}
    for g in groups:
        chosen: dict[int, list] = {}
        for close, vec, won, price in g:
            b = int(price / BUCKET)
            best = chosen.get(b)
            if best is None or abs(vec[2] - horizon_days) < abs(best[1][2] - horizon_days):
                chosen[b] = [close, vec, won, price]
        for b, (_, _, won, price) in chosen.items():
            row = buckets.setdefault(str(b), {"n": 0, "wins": 0, "price_sum": 0.0})
            row["n"] += 1
            row["wins"] += won
            row["price_sum"] += price
    table = {}
    for b, row in sorted(buckets.items(), key=lambda kv: int(kv[0])):
        avg_price = row["price_sum"] / row["n"]
        table[b] = {"n": row["n"], "win_rate": row["wins"] / row["n"], "avg_price": avg_price,
                    "estimate": (row["wins"] + SHRINK * avg_price) / (row["n"] + SHRINK)}
    return {"bucket": BUCKET, "shrink": SHRINK, "buckets": table}


def save(table: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(table, f, indent=2)


_cache: dict[str, dict | None] = {}


def load(path: str) -> dict | None:
    if path not in _cache:
        _cache[path] = None
        if os.path.exists(path):
            with open(path) as f:
                _cache[path] = json.load(f)
    return _cache[path]


def estimate(table: dict, price: float) -> tuple[float, int] | None:
    """Calibrated win probability at this price and the number of markets behind it."""
    row = table["buckets"].get(str(int(price / table["bucket"])))
    if not row:
        return None
    # Apply the bucket's measured bias (estimate - avg_price) to this exact price.
    return min(0.99, max(0.01, price + row["estimate"] - row["avg_price"])), row["n"]
