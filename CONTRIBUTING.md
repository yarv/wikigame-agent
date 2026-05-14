# Contributing

Thanks for your interest! Issues and pull requests are welcome.

## Development setup

```bash
uv sync --all-extras
cp .env.example .env   # fill in at least one model API key
```

## Before you submit a PR

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

CI runs the same checks on Python 3.11, 3.12, and 3.13.

## What I'm looking for

- **New agent strategies.** The current three (`basic`, `react`, `history`) are baselines — there's plenty of room for smarter approaches (planning, link-graph reasoning, better memory).
- **Bug fixes and reliability improvements** to `wiki_client.py` — especially edge cases around disambiguation, redirects, or rate-limit handling.
- **Tests** that mock the MediaWiki API via `respx`; don't add tests that hit the live network.

## What I'd rather you open an issue first for

- Refactors that touch most of the codebase.
- New dependencies.
- Changes to the "agent only sees current page" rule — this is a deliberate fair-play design choice (see [README](README.md#design-notes)).

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
