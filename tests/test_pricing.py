from __future__ import annotations

from inspect_ai.model import ModelUsage, get_model_info
from inspect_ai.model._model import compute_model_cost

from wikigame_agent import pricing


def test_register_prices_populates_inspect_db_for_defaults():
    pricing.register_prices()
    # Every default model id used by the CLI must end up with cost data — these
    # all return cost=None in inspect-ai's bundled DB.
    for model_id in (
        "openai/gpt-5.4-nano",
        "openai/gpt-4o-mini",
        "anthropic/claude-haiku-4-5",
    ):
        info = get_model_info(model_id)
        assert info is not None, f"{model_id} not registered"
        assert info.cost is not None, f"{model_id} has no cost"


def test_registered_cost_computes_expected_dollar_figure():
    pricing.register_prices()
    info = get_model_info("anthropic/claude-haiku-4-5")
    # Haiku 4.5 list price: $1.00 / 1M in, $5.00 / 1M out, $0.10 / 1M cached read.
    # 1M in + 500K out + 100K cached → 1.00 + 2.50 + 0.01 = $3.51.
    usage = ModelUsage(
        input_tokens=1_000_000,
        output_tokens=500_000,
        input_tokens_cache_read=100_000,
    )
    assert abs(compute_model_cost(info.cost, usage) - 3.51) < 1e-6


def test_register_prices_is_idempotent():
    n1 = pricing.register_prices()
    n2 = pricing.register_prices()
    assert n1 == n2
