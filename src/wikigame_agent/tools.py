from __future__ import annotations

import re

from inspect_ai.tool import Tool, tool

from .game import WikiGame, WikiGameRules
from .wiki_client import WikiClientError


def _wrap_links(content: str, permitted_links: list[str]) -> str:
    """Wrap the first occurrence of each permitted link in <link></link> tags.

    Sorted by length descending so multi-word titles wrap before any shorter
    title contained within them ("United States" before "States")."""
    for word in sorted(permitted_links, key=len, reverse=True):
        content = re.sub(
            r"""(\s|[,.)!?;:'"])(""" + re.escape(word) + r""")(\s|[,.)!?;:'"s])""",
            r"\1<link>\2</link>\3",
            content,
            count=1,
            flags=re.IGNORECASE,
        )
    return content


@tool
def get_content(game: WikiGame) -> Tool:
    async def execute() -> str:
        """Get the full content of the Wikipedia page you are currently on.

        Anything corresponding to a link you can follow is wrapped in
        <link></link> tags.

        Returns:
            The content of the current page with permitted links tagged.
        """
        permitted = game.get_permitted_links()
        return _wrap_links(game.current_page.content, permitted)

    return execute


@tool
def move_page(game: WikiGame) -> Tool:
    async def execute(page: str) -> str:
        """Move to a new Wikipedia page by clicking a link in the current page.

        Modifies game state in place. The page title must match (case-insensitive)
        one of the links wrapped in <link></link> tags on the current page.

        Args:
            page: Title of the destination page. Underscores are accepted in
              place of spaces.

        Returns:
            A message describing whether the move succeeded.
        """
        candidate = page.replace("_", " ")
        if not game.is_permitted_link(candidate):
            return (
                f"Move failed: {candidate!r} is not a permitted link from the "
                f"current page ({game.current_page.title!r}). You can only move "
                f"to pages wrapped in <link></link> tags in the content."
            )
        try:
            new_page = await game._client.get_page(candidate)
        except WikiClientError as e:
            return f"Move failed: could not load page {candidate!r}: {e}"

        if isinstance(game, WikiGameRules):
            violation = game.violates_rules(new_page)
            if violation:
                return f"Move failed: {violation}"

        await game.move_to(candidate)
        if game.check_win():
            return f"Move successful — you have reached the goal page {new_page.title!r}."
        return f"Move successful. You are now on {new_page.title!r}."

    return execute


@tool
def check_path(game: WikiGame) -> Tool:
    async def execute(path: str) -> str:
        """Dry-run a proposed path of Wikipedia pages without committing to it.

        The path should be a series of page titles separated by ' -> '. The
        path must start at the current page. It does not have to end at the
        goal. The path is not actually traversed — game state is unchanged.

        Args:
            path: Pages separated by ' -> '. Example: "Canada -> Comedy -> Monty Python".

        Returns:
            Either confirmation that every step is a permitted link from the
            previous page, or a description of the first broken step.
        """
        steps = [s.strip() for s in re.split(r"\s*->\s*", path) if s.strip()]
        if len(steps) < 2:
            return "Path must contain at least two pages separated by '->'."
        if steps[0].lower() != game.current_page.title.lower():
            return (
                f"Path must start with the current page "
                f"({game.current_page.title!r}), not {steps[0]!r}."
            )

        client = game._client
        try:
            cursor = await client.get_page(steps[0])
        except WikiClientError as e:
            return f"Could not load starting page {steps[0]!r}: {e}"

        for i, next_title in enumerate(steps[1:], start=1):
            permitted = cursor.permitted_links()
            if next_title.lower() not in {p.lower() for p in permitted}:
                return f"Path breaks at step {i}: {next_title!r} is not a link in {cursor.title!r}."
            try:
                cursor = await client.get_page(next_title)
            except WikiClientError as e:
                return f"Could not load page {next_title!r} at step {i}: {e}"

            if cursor.title.lower() == game.goal_page.title.lower():
                return (
                    f"Path is valid and reaches the goal at step {i}: {' -> '.join(steps[: i + 1])}"
                )

        return f"Path is valid for all {len(steps)} steps but does not reach the goal."

    return execute
