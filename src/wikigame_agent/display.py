"""Rich-based per-turn game display.

Subscribes to `WikiGame` move events and prints a panel showing each move and
the running path. Designed to coexist with `inspect_ai`'s own progress display
when run with `display='plain'`."""

from __future__ import annotations

from collections.abc import Mapping

from inspect_ai.model import ModelUsage
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .game import WikiGame
from .wiki_client import WikiPage

console = Console()


def print_banner(
    game: WikiGame,
    model: str,
    message_limit: int,
    turn_limit: int | None = None,
    rules: list[str] | None = None,
    notes: bool = False,
) -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("Start", Text(game.starting_page.title, style="bold"))
    table.add_row("Goal", Text(game.goal_page.title, style="bold"))
    table.add_row("Model", model)
    if notes:
        table.add_row("Notes", "on")
    if turn_limit is not None:
        table.add_row("Turn limit", str(turn_limit))
    table.add_row("Message limit", str(message_limit))
    if rules:
        table.add_row("Rules", ", ".join(rules))
    console.print(Panel(table, title="Wiki Game", border_style="cyan"))


def attach(game: WikiGame) -> None:
    """Wire `print_move` to fire on every successful move."""

    def on_move(_game: WikiGame, previous: WikiPage, current: WikiPage) -> None:
        print_move(game, previous, current)

    game.add_move_listener(on_move)


def print_move(game: WikiGame, previous: WikiPage, current: WikiPage) -> None:
    turn = len(game.page_history) - 1
    style = "green" if game.check_win() else "blue"
    body = Text.assemble(
        ("Move ", "dim"),
        (f"{turn}: ", "bold"),
        (previous.title, "default"),
        ("  ->  ", "dim"),
        (current.title, "bold"),
    )
    if game.check_win():
        body.append("\nReached goal page.", style="bold green")
    console.print(Panel(body, border_style=style, expand=False))


_REASON_TITLES = {
    "reached_goal": ("Goal reached", "green"),
    "turn_limit": ("Stopped: turn limit", "yellow"),
    "cycle": ("Stopped: cycle detected", "yellow"),
}


def print_summary(
    game: WikiGame,
    usage: Mapping[str, ModelUsage] | None = None,
) -> None:
    won = game.check_win()
    turns = len(game.page_history) - 1
    reason = getattr(game, "termination_reason", None)
    if won and reason is None:
        reason = "reached_goal"
    title, color = _REASON_TITLES.get(reason or "", ("Game ended without reaching goal", "yellow"))

    rolled = _roll_up(usage) if usage else None

    body = Text.assemble(
        (f"Turns: {turns}\n", "dim"),
        ("Path: ", "dim"),
        (" -> ".join(game.page_history)),
    )
    if not won and reason in ("turn_limit", "cycle"):
        detail = _reason_detail(reason, game.page_history)
        body.append("\n")
        body.append(detail, style="yellow")
    if rolled is not None:
        body.append("\n")
        body.append(_format_usage_line(rolled), style="dim")
        body.append("\n")
        body.append(_format_cost_line(rolled), style="bold")
    console.print(Panel(body, title=title, border_style=color))


def _reason_detail(reason: str, page_history: list[str]) -> str:
    if reason == "turn_limit":
        return f"Reason: turn limit reached after {len(page_history) - 1} moves."
    if reason == "cycle":
        seen: list[str] = []
        for title in page_history[-4:]:
            if title not in seen:
                seen.append(title)
        return "Reason: cycle detected — " + " <-> ".join(seen)
    return ""


def _roll_up(usage: Mapping[str, ModelUsage]) -> ModelUsage:
    total = ModelUsage()
    for u in usage.values():
        total = total + u
    return total


def _format_usage_line(usage: ModelUsage) -> str:
    parts = [
        f"in {usage.input_tokens:,}",
        f"out {usage.output_tokens:,}",
    ]
    if usage.input_tokens_cache_read:
        parts.append(f"cache {usage.input_tokens_cache_read:,}")
    if usage.reasoning_tokens:
        parts.append(f"reasoning {usage.reasoning_tokens:,}")
    return f"Tokens: {usage.total_tokens:,} ({', '.join(parts)})"


def _format_cost_line(usage: ModelUsage) -> str:
    if usage.total_cost is None:
        return "Cost: — (model not in pricing data)"
    return f"Cost: ${usage.total_cost:.4f}"
