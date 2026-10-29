"""Step 3: Prediction agent. Estimates the true probability and decides whether to fire.

  1. Base estimate: the XGBoost calibration model, if it beat the market on held-out
     markets when last trained; otherwise the simple favourite-longshot adjustment.
  2. Claude's read of the research can nudge that estimate, by at most a few cents.
  3. A confidence score combines how trustworthy the base model is with whether the
     research agrees. The agent fires only when edge and confidence both clear their bars.
"""
import json
import os
import time
from dataclasses import dataclass, field

from .. import calibration, features
from ..config import Config
from .research import Research
from .scan import Candidate

_model = None
_meta = None


def load_model(cfg: Config):
    """The trained model if it exists and beat the market in testing, else None."""
    global _model, _meta
    if _meta is None:
        if not (os.path.exists(cfg.model_path) and os.path.exists(cfg.model_meta_path)):
            _meta = {}
            return None
        with open(cfg.model_meta_path) as f:
            _meta = json.load(f)
        if _meta.get("beats_market") and _meta.get("features") == features.FEATURES:
            import xgboost as xgb
            _model = xgb.Booster()
            _model.load_model(cfg.model_path)
    return _model


def model_meta() -> dict:
    return _meta or {}


@dataclass
class Prediction:
    candidate: Candidate
    p_market: float
    p_base: float
    method: str
    p_llm: float | None
    p_final: float
    cost: float                 # all-in price per share including taker fee
    edge: float
    confidence: float
    fire: bool
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"p_market": round(self.p_market, 4), "p_base": round(self.p_base, 4),
                "method": self.method, "p_llm": self.p_llm, "p_final": round(self.p_final, 4),
                "cost": round(self.cost, 4), "edge": round(self.edge, 4),
                "confidence": round(self.confidence, 3), "reasons": self.reasons}


def base_probability(c: Candidate, history, cfg: Config) -> tuple[float, str]:
    """XGBoost if it passed its test, else the calibration table, else the market price."""
    o = c.outcome
    mid = (o.bid + o.ask) / 2
    model = load_model(cfg)
    if model is not None and history and c.market.end_date:
        row = features.build(history, time.time(), c.market.end_date.timestamp(),
                             c.market.category, price=mid)
        if row:
            import xgboost as xgb
            return float(model.predict(xgb.DMatrix([features.vector(row)]))[0]), "xgboost"
    table = calibration.load(cfg.calibration_path)
    est = calibration.estimate(table, mid) if table else None
    if est:
        return est[0], f"calibration table ({est[1]} past markets)"
    return mid, "market price (no calibration data)"


def predict(c: Candidate, research: Research, history, cfg: Config,
            caution_categories: set[str] = frozenset()) -> Prediction:
    o, m = c.outcome, c.market
    p_market = (o.bid + o.ask) / 2
    p_base, method = base_probability(c, history, cfg)
    reasons = [f"market says {p_market*100:.0f}%", f"{method} says {p_base*100:.1f}%"]

    confidence = {"xgboost": 0.65}.get(method, 0.6 if method.startswith("calibration") else 0.5)
    p_final = p_base
    if research.llm_probability is not None:
        shift = cfg.llm_weight * (research.llm_probability - p_base)
        shift = max(-cfg.llm_max_shift, min(cfg.llm_max_shift, shift))
        p_final = p_base + shift
        gap = research.llm_probability - p_market
        reasons.append(f"Claude reads the news as {research.llm_probability*100:.0f}%")
        if gap >= -0.02:
            confidence += 0.10
        elif gap < -0.05:
            confidence -= 0.25
            reasons.append("news points the other way")
        else:
            confidence -= 0.05
        if research.stance is not None and research.stance <= -0.5:
            confidence -= 0.10
    elif research.items:
        reasons.append(f"{len(research.items)} headlines found, not scored (no Claude API key)")
    if m.category in caution_categories:
        confidence -= 0.10
        reasons.append(f"past losses flagged '{m.category}' markets for extra caution")

    cost = o.ask + m.taker_fee(o.ask)
    edge = p_final - cost
    fire = edge >= cfg.min_edge and confidence >= cfg.min_confidence
    reasons.append(f"edge {edge*100:+.1f}c after fees, confidence {confidence:.2f}")
    return Prediction(c, p_market, p_base, method, research.llm_probability,
                      min(0.99, p_final), cost, edge, round(confidence, 3), fire, reasons)
