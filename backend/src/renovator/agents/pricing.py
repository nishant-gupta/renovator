"""Rough per-model USD/MTok list prices for the local cost dashboard
(Phase 9 — an alternative to LangSmith that needs no external account).

Not billing-accurate: real invoices reflect prompt-caching discounts (a
cached input token costs a fraction of an uncached one, and this app's
usage is cache-heavy — see AIMessage.usage_metadata's input_token_details)
that aren't modeled here. Treat every estimated_cost_usd as a ballpark for
spotting trends, not a receipt.
"""

from __future__ import annotations

# (input $/MTok, output $/MTok), approximate public list prices, matched
# by prefix so a dated/suffixed model id (e.g. "claude-haiku-4-5-20251001")
# still resolves.
_PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
_DEFAULT_PRICE = (3.0, 15.0)


def _price_for(model: str) -> tuple[float, float]:
    for prefix, price in _PRICING_PER_MTOK.items():
        if model.startswith(prefix):
            return price
    return _DEFAULT_PRICE


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    input_price, output_price = _price_for(model)
    return (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price
