"""Features for the calibration model, built only from what was known at time t."""
import math

FEATURES = ["price", "logit", "days_to_close", "change_1d", "change_7d",
            "volatility_3d", "range_7d", "cat_sports", "cat_crypto", "cat_politics"]

DAY = 86400


def _price_at(history: list[tuple[int, float]], ts: float) -> float | None:
    """Last known price at or before ts (history is oldest first)."""
    last = None
    for t, p in history:
        if t > ts:
            break
        last = p
    return last


def build(history: list[tuple[int, float]], t: float, close_ts: float, category: str,
          price: float | None = None) -> dict | None:
    """Feature row for one outcome at time t. `price` overrides the history price (live quotes)."""
    p = price if price is not None else _price_at(history, t)
    if p is None or not 0.01 < p < 0.99:
        return None
    window = [q for ts, q in history if t - 7 * DAY <= ts <= t]
    recent = [q for ts, q in history if t - 3 * DAY <= ts <= t]
    diffs = [b - a for a, b in zip(recent, recent[1:])]
    p1, p7 = _price_at(history, t - DAY), _price_at(history, t - 7 * DAY)
    return {
        "price": p,
        "logit": math.log(p / (1 - p)),
        "days_to_close": max(0.0, (close_ts - t) / DAY),
        "change_1d": p - p1 if p1 is not None else 0.0,
        "change_7d": p - p7 if p7 is not None else 0.0,
        "volatility_3d": (sum(d * d for d in diffs) / len(diffs)) ** 0.5 if diffs else 0.0,
        "range_7d": (max(window) - min(window)) if window else 0.0,
        "cat_sports": float(category == "sports"),
        "cat_crypto": float(category == "crypto"),
        "cat_politics": float(category == "politics"),
    }


def mirror(history: list[tuple[int, float]]) -> list[tuple[int, float]]:
    """The other outcome's price history (they always sum to 1)."""
    return [(t, 1 - p) for t, p in history]


def vector(row: dict) -> list[float]:
    return [row[f] for f in FEATURES]
