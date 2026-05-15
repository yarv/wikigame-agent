#!/usr/bin/env python3
"""Generate `MODEL_PRICES.md` and the runtime `model_prices.json` from LiteLLM.

Neither Anthropic nor OpenAI exposes per-token prices through their API
(only `/v1/models` for availability), so we pull from the community-
maintained `model_prices_and_context_window.json` in LiteLLM.

Outputs:
- `MODEL_PRICES.md` at the repo root — human-readable table for the README/docs.
- `src/wikigame_agent/data/model_prices.json` — slim form (openai + anthropic
  chat models, $/token only) loaded by `wikigame_agent.pricing` at runtime so
  inspect-ai can compute per-run cost for models its own DB doesn't cover.

Run: `uv run python scripts/check_model_prices.py`
(stdlib only, so `python scripts/check_model_prices.py` works in CI too.)
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

LITELLM_PRICES_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
)
PROVIDERS = ("anthropic", "openai")
REPO_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_PATH = REPO_ROOT / "MODEL_PRICES.md"
JSON_PATH = REPO_ROOT / "src" / "wikigame_agent" / "data" / "model_prices.json"


def fetch_prices() -> dict[str, dict]:
    with urllib.request.urlopen(LITELLM_PRICES_URL, timeout=30) as resp:
        return json.load(resp)


def per_million(cost_per_token: float | None) -> str:
    if cost_per_token is None:
        return "—"
    return f"${cost_per_token * 1_000_000:.2f}"


def format_int(value: int | None) -> str:
    return f"{value:,}" if value else "—"


def make_row(model_id: str, info: dict) -> str:
    cells = [
        f"`{model_id}`",
        per_million(info.get("input_cost_per_token")),
        per_million(info.get("cache_read_input_token_cost")),
        per_million(info.get("output_cost_per_token")),
        format_int(info.get("max_input_tokens") or info.get("max_tokens")),
        format_int(info.get("max_output_tokens")),
    ]
    return "| " + " | ".join(cells) + " |"


def render_section(provider: str, prices: dict[str, dict]) -> str:
    rows = [
        make_row(model_id, info)
        for model_id, info in sorted(prices.items())
        if isinstance(info, dict)
        and info.get("litellm_provider") == provider
        and info.get("mode") == "chat"
    ]
    header = (
        "| Model | Input / 1M | Cached input / 1M | Output / 1M | "
        "Context | Max output |\n"
        "| --- | ---: | ---: | ---: | ---: | ---: |"
    )
    return f"## {provider.title()}\n\n{header}\n" + "\n".join(rows)


def render(prices: dict[str, dict]) -> str:
    sections = "\n\n".join(render_section(p, prices) for p in PROVIDERS)
    return (
        "# Model prices\n\n"
        f"Chat models from [LiteLLM's pricing data]({LITELLM_PRICES_URL}). "
        "Prices are USD per 1M tokens. Refreshed weekly by the "
        "`model-prices` workflow; see git history for the last update.\n\n"
        f"{sections}\n"
    )


def slim_json(prices: dict[str, dict]) -> dict:
    """The subset `wikigame_agent.pricing` actually consumes at runtime.

    Sorted dict keyed by `<provider>/<model_id>` so JSON diffs in PRs stay
    minimal — only entries whose prices actually moved show up.
    """
    out: dict[str, dict] = {}
    for model_id, info in prices.items():
        if not isinstance(info, dict):
            continue
        provider = info.get("litellm_provider")
        if provider not in PROVIDERS or info.get("mode") != "chat":
            continue
        if info.get("input_cost_per_token") is None:
            continue
        entry: dict[str, float | None] = {
            "input": info["input_cost_per_token"],
            "output": info.get("output_cost_per_token") or 0.0,
            "cache_read": info.get("cache_read_input_token_cost"),
            "cache_write": info.get("cache_creation_input_token_cost"),
        }
        out[f"{provider}/{model_id}"] = entry
    return {"_source": LITELLM_PRICES_URL, "models": dict(sorted(out.items()))}


def main() -> None:
    prices = fetch_prices()
    MARKDOWN_PATH.write_text(render(prices))
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(slim_json(prices), indent=2) + "\n")
    print(f"wrote {MARKDOWN_PATH}")
    print(f"wrote {JSON_PATH}")


if __name__ == "__main__":
    main()
