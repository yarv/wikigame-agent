"""Register OpenAI + Anthropic prices with inspect-ai's cost machinery.

inspect-ai has all the infrastructure to compute `ModelUsage.total_cost` per
call (see `inspect_ai.model._model.compute_model_cost`), but its bundled
model DB ships with `cost=None` for every OpenAI and Anthropic entry. Without
populated cost data, runs report tokens but no dollar figure.

We close the gap by loading the bundled `data/model_prices.json` (refreshed
weekly from LiteLLM by `scripts/check_model_prices.py`) and calling
`set_model_cost` / `set_model_info`. After `register_prices()` runs, every
subsequent `get_model().generate()` populates `usage.total_cost`, and
`EvalLog.stats.model_usage[model].total_cost` rolls up across the run.
"""

from __future__ import annotations

import json
import logging
from importlib.resources import files

from inspect_ai.model import (
    ModelInfo,
    get_model_info,
    set_model_cost,
    set_model_info,
)
from inspect_ai.model._model_data.model_data import ModelCost

logger = logging.getLogger(__name__)

_PRICES_RESOURCE = "data/model_prices.json"


def _load_prices() -> dict[str, dict[str, float | None]]:
    raw = json.loads(files("wikigame_agent").joinpath(_PRICES_RESOURCE).read_text())
    return raw.get("models", {})


def _to_model_cost(entry: dict[str, float | None]) -> ModelCost:
    # Our JSON stores $/token (LiteLLM's native unit); inspect-ai's ModelCost
    # is $/million tokens. Scale here so downstream math stays in inspect's
    # convention.
    def per_million(value: float | None) -> float:
        return (value or 0.0) * 1_000_000

    return ModelCost(
        input=per_million(entry.get("input")),
        output=per_million(entry.get("output")),
        input_cache_read=per_million(entry.get("cache_read")),
        input_cache_write=per_million(entry.get("cache_write")),
    )


def register_prices() -> int:
    """Populate inspect-ai's cost data for OpenAI + Anthropic chat models.

    Returns the number of models registered. Safe to call multiple times.
    """
    prices = _load_prices()
    for model_id, entry in prices.items():
        cost = _to_model_cost(entry)
        if get_model_info(model_id) is not None:
            set_model_cost(model_id, cost)
        else:
            set_model_info(model_id, ModelInfo(cost=cost))
    logger.debug("registered prices for %d models", len(prices))
    return len(prices)
