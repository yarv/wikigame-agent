"""Centralized prompts for the wiki-game agents."""

from __future__ import annotations

from .game import WikiGame

SYSTEM_REACT = (
    "You are a Wikipedia-racing AI. Your goal is to reach a target page by "
    "following links from Wikipedia pages.\n\n"
    "Each turn, first reason explicitly about which link is most likely to "
    "lead toward the goal, paying attention to the path you have already "
    "taken. If your current strategy isn't working, change it. Then call a "
    "tool to act."
)


def on_page(game: WikiGame, rules: list[str] | None = None) -> str:
    parts = [
        f"You are currently on page: {game.current_page.title!r}.",
        f"Your goal page is: {game.goal_page.title!r}.",
    ]
    if rules:
        parts.append(
            "Rules in effect (moves violating these will be rejected): " + "; ".join(rules) + "."
        )
    if len(game.page_history) > 1:
        parts.append("Path so far: " + " -> ".join(game.page_history))
    return "\n\n".join(parts)


STEP_PROMPT = "Think step by step about your next move, then act."

# Used only when the move turn is split into two calls (`--proxy-reasoning`).
REASON_PROMPT = (
    "Think step by step. Which link from the current page is most likely "
    "to lead toward the goal, and why?"
)
ACT_PROMPT = "Now act on your reasoning."

# Fair-play note: this only references pages already in the agent's own
# `page_history` (which it already sees via `on_page`'s "Path so far:" line),
# so it doesn't leak information about the goal page or its link graph.
CYCLE_NUDGE_TEMPLATE = (
    "You appear to be cycling between {pages}. Reconsider whether moving from "
    "your current page is actually making progress toward the goal. If the "
    "obvious-looking link keeps sending you back, try a less obvious one."
)


def cycle_nudge(pages: list[str]) -> str:
    """Format the cycle-nudge message from a list of page titles.

    Renders the pages as `'A' and 'B'` (two pages) or `'A', 'B', and 'C'`
    (more)."""
    quoted = [repr(p) for p in pages]
    if len(quoted) == 2:
        joined = " and ".join(quoted)
    else:
        joined = ", ".join(quoted[:-1]) + f", and {quoted[-1]}"
    return CYCLE_NUDGE_TEMPLATE.format(pages=joined)
