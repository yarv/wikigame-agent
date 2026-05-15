"""Centralized prompts for the wiki-game agents."""

from __future__ import annotations

from .game import WikiGame

SYSTEM_BASIC = (
    "You are a Wikipedia-racing AI. Your aim is to reach a goal page by "
    "following links from a series of Wikipedia pages."
)

SYSTEM_REACT = (
    "You are a Wikipedia-racing AI. Your goal is to reach a target page by "
    "following links from Wikipedia pages.\n\n"
    "Each turn, first reason explicitly about which link is most likely to "
    "lead toward the goal, paying attention to the path you have already "
    "taken. If your current strategy isn't working, change it. Then call a "
    "tool to act."
)


def on_page(game: WikiGame) -> str:
    parts = [
        f"You are currently on page: {game.current_page.title!r}.",
        f"Your goal page is: {game.goal_page.title!r}.",
    ]
    if len(game.page_history) > 1:
        parts.append("Path so far: " + " -> ".join(game.page_history))
    return "\n\n".join(parts)


NEXT_STEP = "What will you do next?"

STEP_PROMPT = "Think step by step about your next move, then act."

# Used only when the move turn is split into two calls (`--proxy-reasoning`).
REASON_PROMPT = (
    "Think step by step. Which link from the current page is most likely "
    "to lead toward the goal, and why?"
)
ACT_PROMPT = "Now act on your reasoning."
