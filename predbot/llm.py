"""Thin wrapper around the Claude API. Every caller copes with None (no key, refusal, error).

Every call's token usage and estimated cost is appended to a JSONL log, which the
dashboard sums into the "Claude API spend" panel.
"""
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)
_client = None
_log_lock = threading.Lock()

# US dollars per million tokens (input, output), first-party API list prices.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
}
# Models that accept the server-side refusal fallback. Sending it to others is a 400.
FALLBACK_OK = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-opus-5", "claude-fable-5-1"}


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _get_client():
    global _client
    if _client is None:
        import anthropic
        # Talk to the public API directly, not whatever ANTHROPIC_BASE_URL this machine sets.
        _client = anthropic.Anthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            base_url=os.environ.get("PREDBOT_ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
        )
    return _client


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = PRICES.get(model, PRICES["claude-opus-5-5"])   # unknown: assume the dearer
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


def record(path: str | None, model: str, purpose: str, usage) -> None:
    if not path or usage is None:
        return
    tokens_in = (getattr(usage, "input_tokens", 0) or 0) \
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0) \
        + (getattr(usage, "cache_read_input_tokens", 0) or 0)
    tokens_out = getattr(usage, "output_tokens", 0) or 0
    row = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": model,
           "purpose": purpose, "input_tokens": tokens_in, "output_tokens": tokens_out,
           "cost_usd": round(cost_usd(model, tokens_in, tokens_out), 6)}
    with _log_lock, open(path, "a") as f:
        f.write(json.dumps(row) + "\n")


def ask(system: str, prompt: str, schema: type[T], model: str, effort: str = "low",
        purpose: str = "other", usage_path: str | None = None) -> T | None:
    """One structured call. Returns a validated `schema` instance, or None."""
    if not available():
        return None
    import anthropic
    extra = {}
    if model in FALLBACK_OK:
        extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    try:
        response = _get_client().beta.messages.parse(
            model=model,
            max_tokens=4000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=schema,
            output_config={"effort": effort},
            **extra,
        )
    except anthropic.RateLimitError as e:
        print(f"LLM rate-limited, skipping: {e}", flush=True)
        return None
    except anthropic.APIStatusError as e:
        print(f"LLM error {e.status_code}, skipping: {e.message}", flush=True)
        return None
    except anthropic.APIConnectionError as e:
        print(f"LLM unreachable, skipping: {e}", flush=True)
        return None
    # Billed even when refused, so record before checking.
    record(usage_path, getattr(response, "model", None) or model, purpose, response.usage)
    if response.stop_reason == "refusal":
        return None
    return response.parsed_output


def spend_summary(path: str) -> dict:
    """Totals for the dashboard: all time, today, last 7 days, and by purpose and model."""
    out = {"total": 0.0, "today": 0.0, "week": 0.0, "calls": 0, "by_purpose": {}, "by_model": {},
           "first": None}
    if not os.path.exists(path):
        return out
    now = datetime.now(timezone.utc)
    today, week_ago = now.date().isoformat(), now - timedelta(days=7)
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            c = r["cost_usd"]
            out["total"] += c
            out["calls"] += 1
            out["first"] = out["first"] or r["at"]
            if r["at"][:10] == today:
                out["today"] += c
            if datetime.fromisoformat(r["at"]) >= week_ago:
                out["week"] += c
            p = out["by_purpose"].setdefault(r["purpose"], {"cost": 0.0, "calls": 0})
            p["cost"] += c
            p["calls"] += 1
            m = out["by_model"].setdefault(r["model"], {"cost": 0.0, "calls": 0})
            m["cost"] += c
            m["calls"] += 1
    return out
