from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal

from .wiki_client import WikiClient, WikiPage

Rule = Literal["no countries", "no cities"]

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
    ):
        self.client = client
        self.starting_page = starting_page
        self.goal_page = goal_page
        self.current_page = starting_page
        self.page_history: list[str] = [starting_page.title]
        self._move_listeners: list[MoveListener] = []

    @classmethod
    async def create(
        cls,
        client: WikiClient,
        starting_page: str,
        goal_page: str,
    ) -> WikiGame:
        start = await client.get_page(starting_page)
        goal = await client.get_page(goal_page)
        return cls(client, start, goal)

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
        return self.current_page.title == self.goal_page.title


class WikiGameRules(WikiGame):
    """WikiGame with optional rule constraints on which pages can be visited."""

    def __init__(
        self,
        client: WikiClient,
        starting_page: WikiPage,
        goal_page: WikiPage,
        rules: list[Rule] | None = None,
    ):
        super().__init__(client, starting_page, goal_page)
        self.rules: list[Rule] = list(rules or [])

    @classmethod
    async def create(  # type: ignore[override]
        cls,
        client: WikiClient,
        starting_page: str,
        goal_page: str,
        rules: list[Rule] | None = None,
    ) -> WikiGameRules:
        base = await WikiGame.create(client, starting_page, goal_page)
        return cls(base.client, base.starting_page, base.goal_page, rules)

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
