"""Thin wrapper around the Claude API. Every caller copes with None (no key, refusal, error)."""
import os
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)
_client = None


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


def ask(system: str, prompt: str, schema: type[T], model: str, effort: str = "low") -> T | None:
    """One structured call. Returns a validated `schema` instance, or None."""
    if not available():
        return None
    import anthropic
    try:
        response = _get_client().beta.messages.parse(
            model=model,
            max_tokens=4000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=schema,
            output_config={"effort": effort},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
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
    if response.stop_reason == "refusal":
        return None
    return response.parsed_output
