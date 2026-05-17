from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal

from .wiki_client import WikiClient, WikiPage

Rule = Literal["no countries", "no cities"]

# Why the run ended. None until the loop sets it (or the summary will fall back
# to a generic "ended without reaching goal" message).
TerminationReason = Literal["reached_goal", "turn_limit", "cycle"]

MoveListener = Callable[["WikiGame", WikiPage, WikiPage], Awaitable[None] | None]


class WikiGame:
    """Wikipedia-racing game state.

    Pages are loaded via the injected `WikiClient`. Construct with `await
    WikiGame.create(client, start, goal)` — the constructor needs to await
    the initial page fetches.
    """

    def __init__(
        self,
        client: WikiClient,
        starting_page: WikiPage,
        goal_page: WikiPage,
        turn_limit: int | None = None,
    ):
        self.client = client
        self.starting_page = starting_page
        self.goal_page = goal_page
        self.current_page = starting_page
        self.page_history: list[str] = [starting_page.title]
        self._move_listeners: list[MoveListener] = []
        self.turn_limit = turn_limit
        self.termination_reason: TerminationReason | None = None

    @classmethod
    async def create(
        cls,
        client: WikiClient,
        starting_page: str,
        goal_page: str,
        turn_limit: int | None = None,
    ) -> WikiGame:
        start = await client.get_page(starting_page)
        goal = await client.get_page(goal_page)
        return cls(client, start, goal, turn_limit=turn_limit)

    def add_move_listener(self, listener: MoveListener) -> None:
        self._move_listeners.append(listener)

    async def move_to(self, title: str) -> WikiPage:
        """Move to a permitted link. Caller must verify with `is_permitted_link`
        first; this method assumes the move is legal."""
        previous = self.current_page
        new_page = await self.client.get_page(title)
        self.current_page = new_page
        self.page_history.append(new_page.title)
        for listener in self._move_listeners:
            result = listener(self, previous, new_page)
            if result is not None:
                await result
        return new_page

    def get_permitted_links(self) -> list[str]:
        return self.current_page.permitted_links()

    def is_permitted_link(self, link: str) -> bool:
        return self.current_page.resolve_link(link) is not None

    def check_win(self) -> bool:
        won = self.current_page.title == self.goal_page.title
        if won and self.termination_reason is None:
            self.termination_reason = "reached_goal"
        return won

    def turn_limit_reached(self) -> bool:
        """True when `turn_limit` is set and the number of moves so far meets
        or exceeds it. Page history starts with the starting page (1 entry,
        0 moves), so the move count is `len(page_history) - 1`."""
        if self.turn_limit is None:
            return False
        return (len(self.page_history) - 1) >= self.turn_limit


class WikiGameRules(WikiGame):
    """WikiGame with optional rule constraints on which pages can be visited."""

    def __init__(
        self,
        client: WikiClient,
        starting_page: WikiPage,
        goal_page: WikiPage,
        rules: list[Rule] | None = None,
        turn_limit: int | None = None,
    ):
        super().__init__(client, starting_page, goal_page, turn_limit=turn_limit)
        self.rules: list[Rule] = list(rules or [])

    @classmethod
    async def create(  # type: ignore[override]
        cls,
        client: WikiClient,
        starting_page: str,
        goal_page: str,
        rules: list[Rule] | None = None,
        turn_limit: int | None = None,
    ) -> WikiGameRules:
        base = await WikiGame.create(client, starting_page, goal_page)
        return cls(base.client, base.starting_page, base.goal_page, rules, turn_limit=turn_limit)

    def violates_rules(self, page: WikiPage) -> str | None:
        """Return a human-readable reason if visiting `page` would violate
        any rule, else None."""
        if "no countries" in self.rules and _is_country(page):
            return "rule violation: target page appears to be a country article"
        if "no cities" in self.rules and _is_city(page):
            return "rule violation: target page appears to be a city article"
        return None


def _is_country(page: WikiPage) -> bool:
    # Cheap heuristic that matches the spirit of the notebook exercise.
    markers = ("is a country", "is a sovereign", "is a landlocked country")
    head = page.content[:2000].lower()
    return any(m in head for m in markers)


def _is_city(page: WikiPage) -> bool:
    markers = (
        "is a city",
        "is a town",
        "is a municipality",
        "is a village",
        "is the capital",
    )
    head = page.content[:2000].lower()
    return any(m in head for m in markers)
