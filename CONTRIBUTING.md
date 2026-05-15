# Contributing

Thanks for your interest! Issues and pull requests are welcome.

## Development setup

```bash
make install           # uv sync --all-extras + installs pre-commit hooks
cp .env.example .env   # fill in at least one model API key
```

If you don't have `make`, the equivalent is:

```bash
uv sync --all-extras
uv run pre-commit install
```

## Before you submit a PR

```bash
make check             # ruff lint + format check + pytest (the same checks CI runs)
```

Or run the steps individually:

```bash
make lint
make format-check
make test
```

Pre-commit will also run ruff on staged files automatically when you `git commit`. To auto-fix lint and formatting in one go: `make fix`.

CI runs `make check` on Python 3.11, 3.12, and 3.13, plus `pre-commit run --all-files`.

## Pull request titles

PR titles must follow [Conventional Commits](https://www.conventionalcommits.org/). Examples:

- `feat: add planning-based agent strategy`
- `fix: handle redirect responses in wiki_client`
- `docs: clarify history-agent behavior in README`
- `chore: bump ruff to 0.8`

Allowed types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `ci`, `build`, `perf`, `revert`. A GitHub Action enforces this. Releases and the changelog are generated automatically from these titles by [release-please](https://github.com/googleapis/release-please) — you don't need to bump the version manually.

Since the project squash-merges, only the PR title matters; individual commits inside the PR don't need to follow the convention.

## What I'm looking for

- **New agent strategies.** The current three (`basic`, `react`, `history`) are baselines — there's plenty of room for smarter approaches (planning, link-graph reasoning, better memory).
- **Bug fixes and reliability improvements** to `wiki_client.py` — especially edge cases around disambiguation, redirects, or rate-limit handling.
- **Tests** that mock the MediaWiki API via `respx`; don't add tests that hit the live network.

## What I'd rather you open an issue first for

- Refactors that touch most of the codebase.
- New dependencies.
- Changes to the "agent only sees current page" rule — this is a deliberate fair-play design choice (see [README](README.md#design-notes)).

## Maintainer notes

### release-please PAT

`.github/workflows/release-please.yml` uses a Personal Access Token (`RELEASE_PLEASE_TOKEN`) instead of the default `GITHUB_TOKEN`. This is so the release PRs it opens trigger CI — GitHub deliberately skips workflows on events caused by `GITHUB_TOKEN` to prevent recursion, which would otherwise leave release PRs unable to satisfy the required-status-check ruleset.

To rotate or recreate the token:

1. Go to https://github.com/settings/personal-access-tokens/new (fine-grained PAT).
2. Repository access: **only** this repo.
3. Permissions:
   - **Contents:** Read and write
   - **Pull requests:** Read and write
4. Expiration: pick something you'll remember to rotate (a year is the max).
5. Save as repo secret `RELEASE_PLEASE_TOKEN` (Settings → Secrets and variables → Actions).

A GitHub App token works as a drop-in replacement (e.g. via `actions/create-github-app-token`) and is preferable if this project ever has multiple maintainers.

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
