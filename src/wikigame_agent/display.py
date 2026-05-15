"""Rich-based per-turn game display.

Subscribes to `WikiGame` move events and prints a panel showing each move and
the running path. Designed to coexist with `inspect_ai`'s own progress display
when run with `display='plain'`."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .game import WikiGame
from .wiki_client import WikiPage

console = Console()


def print_banner(
    game: WikiGame,
    agent_name: str,
    model: str,
    message_limit: int,
    rules: list[str] | None = None,
) -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("Start", Text(game.starting_page.title, style="bold"))
    table.add_row("Goal", Text(game.goal_page.title, style="bold"))
    table.add_row("Agent", agent_name)
    table.add_row("Model", model)
    table.add_row("Message limit", str(message_limit))
    if rules:
        table.add_row("Rules", ", ".join(rules))
    console.print(Panel(table, title="Wiki Game", border_style="cyan"))


def attach(game: WikiGame) -> None:
    """Wire `print_move` to fire on every successful move."""

    def on_move(game: WikiGame, previous: WikiPage, current: WikiPage) -> None:
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


def print_summary(game: WikiGame) -> None:
    won = game.check_win()
    turns = len(game.page_history) - 1
    color = "green" if won else "yellow"
    title = "Goal reached" if won else "Game ended without reaching goal"
    body = Text.assemble(
        (f"Turns: {turns}\n", "dim"),
        ("Path: ", "dim"),
        (" -> ".join(game.page_history)),
    )
    console.print(Panel(body, title=title, border_style=color))
