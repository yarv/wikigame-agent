# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries from v0.2.0 onward are generated automatically by
[release-please](https://github.com/googleapis/release-please) from
[Conventional Commits](https://www.conventionalcommits.org/).

## [0.2.1](https://github.com/yarv/wikigame-agent/compare/wikigame-agent-v0.2.0...wikigame-agent-v0.2.1) (2026-05-15)


### Bug Fixes

* **config:** point default User-Agent at this repo, not claude-code ([#7](https://github.com/yarv/wikigame-agent/issues/7)) ([d81a9ca](https://github.com/yarv/wikigame-agent/commit/d81a9ca9de0fee2444d61d49f58119b507383bcb))

## [0.2.0](https://github.com/yarv/wikigame-agent/compare/wikigame-agent-v0.1.0...wikigame-agent-v0.2.0) (2026-05-15)


### Features

* **agents:** single model call per turn + force get_content before move ([#3](https://github.com/yarv/wikigame-agent/issues/3)) ([8f05e1a](https://github.com/yarv/wikigame-agent/commit/8f05e1a77c7cd6d4e87b8ea9bcdd09f89d79e01e))

## [0.1.0] - 2026-05-14

Initial public release.

### Added
- Three agent strategies: `basic` (reset history on move), `react` (reason-then-act), `history` (ReAct + persistent notes).
- Self-contained MediaWiki client (`wiki_client.py`) with a real User-Agent, exponential-backoff retries, and a clear error on non-JSON responses — fixes the `JSONDecodeError` that the `wikipedia` PyPI package raises when rate-limited.
- `wikigame play` and `wikigame view` CLI commands.
- Rich-based per-turn console display.
- `pytest` + `respx` test suite covering `wiki_client`, `tools`, and `game` (no live network).

[0.1.0]: https://github.com/yarv/wikigame-agent/releases/tag/v0.1.0
