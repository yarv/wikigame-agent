# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries from v0.2.0 onward are generated automatically by
[release-please](https://github.com/googleapis/release-please) from
[Conventional Commits](https://www.conventionalcommits.org/).

## [0.7.1](https://github.com/yarv/wikigame-agent/compare/wikigame-agent-v0.7.0...wikigame-agent-v0.7.1) (2026-05-18)


### Bug Fixes

* **wiki-client:** stop auto-resolving disambiguation pages ([#34](https://github.com/yarv/wikigame-agent/issues/34)) ([012234d](https://github.com/yarv/wikigame-agent/commit/012234da3d02f0297cbdb21e41a3ba902025324d))

## [0.7.0](https://github.com/yarv/wikigame-agent/compare/wikigame-agent-v0.6.1...wikigame-agent-v0.7.0) (2026-05-17)


### ⚠ BREAKING CHANGES

* `--agent` CLI option is removed. The `wikigame_agent.agents` module no longer exports `react_agent`, `history_agent`, `AGENTS`, or `AgentName` — import `wiki_agent` directly.
* `--agent basic` is no longer valid.

### Features

* **agents:** turn-based budget, cycle detection, and graceful loop abort ([#29](https://github.com/yarv/wikigame-agent/issues/29)) ([9234d8a](https://github.com/yarv/wikigame-agent/commit/9234d8a49963d5335ade3899ca98579c2795425e))
* collapse agent strategies into single wiki_agent with --notes flag ([#32](https://github.com/yarv/wikigame-agent/issues/32)) ([aaa33fc](https://github.com/yarv/wikigame-agent/commit/aaa33fc34e6100e01c5d0d366e67ccf3109e9221))
* drop basic agent strategy ([#31](https://github.com/yarv/wikigame-agent/issues/31)) ([4a6ce4d](https://github.com/yarv/wikigame-agent/commit/4a6ce4d0e8f72027f0d142299215e8a1c30f4894))


### Documentation

* detailed install instructions for PyPI + source paths ([#33](https://github.com/yarv/wikigame-agent/issues/33)) ([a98aac1](https://github.com/yarv/wikigame-agent/commit/a98aac10a7058a3a5f01c14eb28b038d88505af3))

## [0.6.1](https://github.com/yarv/wikigame-agent/compare/wikigame-agent-v0.6.0...wikigame-agent-v0.6.1) (2026-05-16)


### Bug Fixes

* **tools:** resolve disambiguated link targets so the agent can click them ([#24](https://github.com/yarv/wikigame-agent/issues/24)) ([55e7b78](https://github.com/yarv/wikigame-agent/commit/55e7b78980eaedbc35e2c1a0298acdb4bdcf80d5))

## [0.6.0](https://github.com/yarv/wikigame-agent/compare/wikigame-agent-v0.5.1...wikigame-agent-v0.6.0) (2026-05-15)


### Features

* **pricing:** weekly model-price refresh + total cost in run summary ([#21](https://github.com/yarv/wikigame-agent/issues/21)) ([66f6271](https://github.com/yarv/wikigame-agent/commit/66f6271d19616f2ae32c2e26d20714e8cbfd1f83))


### Bug Fixes

* **tools:** block moves that redirect back to the current page ([#22](https://github.com/yarv/wikigame-agent/issues/22)) ([0241e64](https://github.com/yarv/wikigame-agent/commit/0241e64d70a9ee4f582202477eed9729f2207ad7))

## [0.5.1](https://github.com/yarv/wikigame-agent/compare/wikigame-agent-v0.5.0...wikigame-agent-v0.5.1) (2026-05-15)


### Documentation

* **contributing:** drop solo-maintainer ops section ([#19](https://github.com/yarv/wikigame-agent/issues/19)) ([4965c07](https://github.com/yarv/wikigame-agent/commit/4965c07d6c34e5de0aa9498a74350618f10326ea))

## [0.5.0](https://github.com/yarv/wikigame-agent/compare/wikigame-agent-v0.4.1...wikigame-agent-v0.5.0) (2026-05-15)


### Features

* **game:** add no-cities rule, surface rules to agent, block self-links ([#16](https://github.com/yarv/wikigame-agent/issues/16)) ([b14dad3](https://github.com/yarv/wikigame-agent/commit/b14dad34b42005607cf766e2d55953713d5c0eb9))

## [0.4.1](https://github.com/yarv/wikigame-agent/compare/wikigame-agent-v0.4.0...wikigame-agent-v0.4.1) (2026-05-15)


### Bug Fixes

* **release-please:** descend into tagged-value when matching uv.lock entry ([#14](https://github.com/yarv/wikigame-agent/issues/14)) ([a94c6d7](https://github.com/yarv/wikigame-agent/commit/a94c6d749e19573a151b1613f68ae06853cdeb2c))

## [0.4.0](https://github.com/yarv/wikigame-agent/compare/wikigame-agent-v0.3.0...wikigame-agent-v0.4.0) (2026-05-15)


### Features

* **display:** drop redundant path line from move panel ([#12](https://github.com/yarv/wikigame-agent/issues/12)) ([4c8c9a4](https://github.com/yarv/wikigame-agent/commit/4c8c9a49a5271196e9eb9f4ae4bcd3f361fb55b0))

## [0.3.0](https://github.com/yarv/wikigame-agent/compare/wikigame-agent-v0.2.1...wikigame-agent-v0.3.0) (2026-05-15)


### Features

* **cli:** name inspect tasks by agent + start/goal pages ([#10](https://github.com/yarv/wikigame-agent/issues/10)) ([3432a62](https://github.com/yarv/wikigame-agent/commit/3432a62b264514a019681ff5eb02fc145eab7ba6))

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
