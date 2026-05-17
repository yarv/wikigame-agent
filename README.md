# wikigame-agent

[![CI](https://github.com/yarv/wikigame-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/yarv/wikigame-agent/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

An LLM agent that plays the [Wikipedia game/Wikiracing](https://en.wikipedia.org/wiki/Wikiracing) (navigate from a starting page to a goal page using only links), built on [AISI Inspect](https://github.com/UKGovernmentBEIS/inspect_ai).

This started as a port of the Chapter 3.4 LLM Agents exercise from [ARENA 3.0](https://github.com/callummcdougall/ARENA_3.0) into a self-contained project. The notable changes over the original notebook:

- A custom MediaWiki client with a real User-Agent, exponential backoff retries, and a clear error when the API returns non-JSON. This eliminates the `JSONDecodeError`s that came from Wikipedia silently rate-limiting the `wikipedia` PyPI package.
- A single agent loop with an opt-in `--notes` mode for carrying reasoning forward across moves.
- `tools.py` with `get_content`, `move_page`, and `check_path` (the last one was unimplemented in the notebook).
- A Rich-based per-turn console display so you can watch the game without spinning up the Inspect log viewer.

## Setup

```bash
uv sync                       # create venv, install
cp .env.example .env          # then fill in OPENAI_API_KEY etc.
```

## Play a game

```bash
uv run wikigame play "Canada" "Monty Python" \
  --model openai/gpt-5.4-nano --reasoning-effort medium
```

Options:

- `--notes` — carry a compact textual record of each prior move's reasoning forward across page transitions. Default off; useful on long-form races where the model otherwise re-explores ideas it has already considered.
- `--model openai/gpt-5.4-nano` — overrides `INSPECT_EVAL_MODEL`
- `--reasoning-effort {none|minimal|low|medium|high|xhigh|max}` — for o-series and gpt-5 models. The agent relies on the model reasoning before each move; on a reasoning model that means setting this to at least `low`. On the OpenAI gpt-5 family the default is `minimal`, which produces no useful reasoning and the agent will flounder.
- `--proxy-reasoning` — for models without native reasoning (e.g. `gpt-4o-mini`) or with reasoning effort set to `minimal`. Splits each move turn into a separate text-only reason call (forced `tool_choice="none"`) followed by an act call, so the model's CoT shows up in plain text. Roughly doubles per-move model calls, so prefer a reasoning model when possible.
- `--turn-limit 40` — max number of moves the agent may make before the run aborts with reason `turn_limit`, counted at the game layer. The agent also auto-detects tight cycles (A↔B oscillation, A→B→C→A): on the first detection it gets a one-shot nudge, on the second it stops with reason `cycle`.
- `--message-limit 240` — hard backstop on Inspect message count; default is set high enough that `--turn-limit` fires first.
- `--enable-check-path` — adds the `check_path` dry-run tool
- `-v` — debug logging

Each move prints a panel like:

```
╭─ Move 1: Canada  ->  British Empire ─╮
│ Path: Canada -> British Empire        │
╰───────────────────────────────────────╯
```

…and a final summary panel showing the full path and whether the goal was reached.

## View Inspect logs

The CLI writes Inspect logs to `./logs/`. To inspect them in the browser:

```bash
uv run wikigame view             # opens http://localhost:7575
# or equivalently:
uv run inspect view --log-dir logs
```

## Development

```bash
make install        # uv sync --all-extras + installs pre-commit hooks
make check          # ruff lint + format check + pytest (everything CI runs)
make help           # list all targets
```

Tests use [respx](https://github.com/lundberg/respx) to mock the MediaWiki API — no network required.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contributor workflow, including the Conventional Commits PR-title convention used to drive automatic version bumps and changelog updates via [release-please](https://github.com/googleapis/release-please).

## Design notes

**The agent only sees the current page.** No goal-page summary, no link list — just the title of where it is, the title of where it's going, and (via `get_content`) the body of the page it's currently on. This mirrors how a human plays and makes results comparable across runs and models.

**Self-contained MediaWiki client.** The popular `wikipedia` PyPI package is unmaintained and crashes with `JSONDecodeError` when Wikipedia rate-limits it (it tries to parse the HTML error page as JSON). [`wiki_client.py`](src/wikigame_agent/wiki_client.py) sets a real User-Agent, retries transient failures, raises a clear error on non-JSON responses, and caches pages in-process.

**One agent loop, two modes.** The agent makes one model call per turn, alternating a forced `get_content` on each new page with a `move_page` call (reasoning text and the tool call come back in one response). On a successful move the message history is rebuilt from scratch. Use `--proxy-reasoning` to split the move turn into a separate reason + act pair for models without native reasoning. Use `--notes` to additionally carry a compact textual record of each prior move's reasoning across transitions, so the model can see *why* it picked each prior page rather than just where it ended up.

## Layout

```
src/wikigame_agent/
  wiki_client.py   # async MediaWiki client (the JSONDecodeError fix lives here)
  game.py          # WikiGame, WikiGameRules
  tools.py         # get_content, move_page, check_path
  prompts.py       # system / on-page / next-step / step
  agents.py        # wiki_agent (the single agent loop)
  display.py       # Rich-based turn-by-turn console output
  cli.py           # `wikigame play ...`, `wikigame view`
  config.py        # pydantic-settings, reads .env
```

## Credits

Original exercise from [ARENA 3.0](https://github.com/callummcdougall/ARENA_3.0), Chapter 3.4 (LLM Agents) by [Callum McDougall](https://github.com/callummcdougall) and contributors.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and PRs welcome.

## License

[Apache License 2.0](LICENSE). Contributions are accepted under the same license.
