"""Train the XGBoost calibration model on resolved Polymarket markets.

Each example is "an outcome priced p, h days before close, with this recent price
path": did it win? The market price itself is the strongest feature, so the
question the model answers is whether prices are systematically off (for example
favourites winning more often than their price says). The newest 20% of markets
are held back as a test set, and the model is only switched on if it beats the
plain market price there.
"""
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor

from . import calibration, features
from .config import Config
from .polymarket import PolymarketClient, parse_market

HORIZONS_DAYS = (1, 2, 3, 5, 7, 10, 14, 21, 30)


def _examples_for(client: PolymarketClient, raw: dict) -> list[tuple[float, list[float], int, float]]:
    m = parse_market(raw)
    if not m or not m.closed_time or not m.start_date or len(m.token_ids) != 2:
        return []
    yes_wins = m.settlement_price(m.token_ids[0])
    if yes_wins is None:
        return []
    close = m.closed_time.timestamp()
    start = m.start_date.timestamp()
    if close - start < 3 * features.DAY:
        return []
    try:
        hist = client.price_history(m.token_ids[0], int(max(start, close - 38 * features.DAY)), int(close))
    except Exception:
        return []
    if len(hist) < 24:
        return []
    out = []
    for h in HORIZONS_DAYS:
        t = close - h * features.DAY
        if t < start + features.DAY:
            continue
        for side_hist, won in ((hist, yes_wins), (features.mirror(hist), 1 - yes_wins)):
            row = features.build(side_hist, t, close, m.category)
            if row and 0.03 <= row["price"] <= 0.97:
                out.append((close, features.vector(row), int(won), row["price"]))
    return out


def _logloss(ys, ps):
    eps = 1e-6
    return -sum(y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps))
                for y, p in zip(ys, ps)) / len(ys)


def _brier(ys, ps):
    return sum((p - y) ** 2 for y, p in zip(ys, ps)) / len(ys)


def train(cfg: Config, pages: int = 40) -> dict:
    import numpy as np
    import xgboost as xgb

    client = PolymarketClient()
    # Two orderings reach different markets, since the API stops paging after ~2,500 rows.
    by_id = {r["id"]: r for order in ("closedTime", "volumeNum")
             for r in client.list_resolved_markets(pages=pages, order=order)}
    raw = list(by_id.values())
    print(f"fetched {len(raw)} resolved markets; pulling price histories...", flush=True)
    with ThreadPoolExecutor(max_workers=cfg.research_workers) as pool:
        groups = list(pool.map(lambda r: _examples_for(client, r), raw))
    groups = [g for g in groups if g]
    with open(cfg.examples_path, "w") as f:    # cached for calibration checks and retraining
        json.dump(groups, f)
    calibration.save(calibration.build(groups), cfg.calibration_path)
    groups.sort(key=lambda g: g[0][0])                      # oldest market first
    split = int(len(groups) * 0.8)
    train_rows = [r for g in groups[:split] for r in g]
    test_rows = [r for g in groups[split:] for r in g]
    print(f"{len(groups)} usable markets -> {len(train_rows)} train / {len(test_rows)} test examples", flush=True)
    if len(groups) < 100:
        raise SystemExit("too few usable markets to train on")

    X = np.array([r[1] for r in train_rows]); y = np.array([r[2] for r in train_rows])
    Xt = np.array([r[1] for r in test_rows]); yt = [r[2] for r in test_rows]
    params = {"objective": "binary:logistic", "eval_metric": "logloss", "max_depth": 3,
              "eta": 0.03, "subsample": 0.8, "colsample_bytree": 0.8,
              "min_child_weight": 25, "lambda": 5.0, "seed": 7}
    model = xgb.train(params, xgb.DMatrix(X, label=y), num_boost_round=300)
    pm = [float(p) for p in model.predict(xgb.DMatrix(Xt))]
    pb = [r[3] for r in test_rows]

    band = [i for i, r in enumerate(test_rows) if cfg.min_entry_price <= r[3] <= cfg.max_entry_price]
    yb = [yt[i] for i in band]
    meta = {
        "markets": len(groups), "train_examples": len(train_rows), "test_examples": len(test_rows),
        "test_logloss_model": _logloss(yt, pm), "test_logloss_market": _logloss(yt, pb),
        "test_brier_model": _brier(yt, pm), "test_brier_market": _brier(yt, pb),
        "band_examples": len(band),
        "band_win_rate": sum(yb) / len(yb) if yb else None,
        "band_avg_price": sum(pb[i] for i in band) / len(band) if band else None,
        "band_brier_model": _brier(yb, [pm[i] for i in band]) if band else None,
        "band_brier_market": _brier(yb, [pb[i] for i in band]) if band else None,
        "features": features.FEATURES,
    }
    meta["beats_market"] = bool(
        meta["test_logloss_model"] < meta["test_logloss_market"]
        and band and meta["band_brier_model"] <= meta["band_brier_market"])
    os.makedirs(os.path.dirname(cfg.model_path) or ".", exist_ok=True)
    model.save_model(cfg.model_path)
    with open(cfg.model_meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    return meta
