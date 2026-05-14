# wikigame-agent

[![CI](https://github.com/yarv/wikigame-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/yarv/wikigame-agent/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

An LLM agent that plays the [Wikipedia game](https://en.wikipedia.org/wiki/Wikipedia:Wikipedia_Game) (navigate from a starting page to a goal page using only links), built on [AISI Inspect](https://github.com/UKGovernmentBEIS/inspect_ai).

This started as a port of the Chapter 3.4 LLM Agents exercise from [ARENA 3.0](https://github.com/callummcdougall/ARENA_3.0) into a self-contained project. The notable changes over the original notebook:

- A custom MediaWiki client with a real User-Agent, exponential backoff retries, and a clear error when the API returns non-JSON. This eliminates the `JSONDecodeError`s that came from Wikipedia silently rate-limiting the `wikipedia` PyPI package.
- Three agent strategies (`basic`, `react`, `history`) selectable from the CLI.
- `tools.py` with `get_content`, `move_page`, and `check_path` (the last one was unimplemented in the notebook).
- A Rich-based per-turn console display so you can watch the game without spinning up the Inspect log viewer.

## Setup

```bash
uv sync                       # create venv, install
cp .env.example .env          # then fill in OPENAI_API_KEY etc.
```

## Play a game

```bash
uv run wikigame play "Canada" "Monty Python"
```

Options:

- `--agent {basic,react,history}` — default `react`
- `--model openai/gpt-4o-mini` — overrides `INSPECT_EVAL_MODEL`
- `--message-limit 80` — Inspect aborts the run past this
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

## Run tests

```bash
uv run pytest
```

Tests use [respx](https://github.com/lundberg/respx) to mock the MediaWiki API — no network required.

## Design notes

**The agent only sees the current page.** No goal-page summary, no link list — just the title of where it is, the title of where it's going, and (via `get_content`) the body of the page it's currently on. This mirrors how a human plays and makes results comparable across runs and models.

**Self-contained MediaWiki client.** The popular `wikipedia` PyPI package is unmaintained and crashes with `JSONDecodeError` when Wikipedia rate-limits it (it tries to parse the HTML error page as JSON). [`wiki_client.py`](src/wikigame_agent/wiki_client.py) sets a real User-Agent, retries transient failures, raises a clear error on non-JSON responses, and caches pages in-process.

**Three agents, increasing in sophistication.**

- `basic`: tool-call loop. Resets message history on every successful move.
- `react`: explicit reason-then-act turns each step.
- `history`: ReAct + carries a compact text record of prior moves across page transitions.

## Layout

```
src/wikigame_agent/
  wiki_client.py   # async MediaWiki client (the JSONDecodeError fix lives here)
  game.py          # WikiGame, WikiGameRules
  tools.py         # get_content, move_page, check_path
  prompts.py       # system / on-page / next-step / reason / act
  agents.py        # basic_agent, react_agent, history_agent
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
