from __future__ import annotations

import re

from inspect_ai.tool import Tool, tool

from .game import WikiGame, WikiGameRules
from .wiki_client import WikiClientError


def _wrap_links(content: str, link_index: dict[str, list[str]]) -> str:
    """Wrap the first occurrence of each display form in <link></link> tags.

    Sorted by length descending so multi-word titles wrap before any shorter
    title contained within them ("United States" before "States"). When a
    display form maps to multiple disambiguated targets (or to a single
    differently-named target like ``"Tangled" -> "Tangled (2010 film)"``),
    the wrapped tag is followed by a parenthetical hint listing the actual
    target page name(s) — agents must call ``move_page`` with one of those
    exact titles to disambiguate."""
    # Pass 1: wrap display forms.
    for form in sorted(link_index.keys(), key=len, reverse=True):
        content = re.sub(
            r"""(\s|[,.)!?;:'"])(""" + re.escape(form) + r""")(\s|[,.)!?;:'"s])""",
            r"\1<link>\2</link>\3",
            content,
            count=1,
            flags=re.IGNORECASE,
        )
    # Pass 2: append disambiguation hints. Done separately so the hint text
    # (which contains other titles) can't accidentally match a later wrap.
    for form, targets in link_index.items():
        if len(targets) > 1:
            hint = f" (one of: {', '.join(targets)})"
        elif targets[0].lower() != form.lower():
            hint = f" (links to: {targets[0]})"
        else:
            continue
        pattern = re.compile(r"<link>(" + re.escape(form) + r")</link>", flags=re.IGNORECASE)
        content = pattern.sub(lambda m, h=hint: f"<link>{m.group(1)}</link>{h}", content, count=1)
    return content


@tool
def get_content(game: WikiGame) -> Tool:
    async def execute() -> str:
        """Get the full content of the Wikipedia page you are currently on.

        Anything corresponding to a link you can follow is wrapped in
        <link></link> tags. When a link's display text could resolve to
        multiple Wikipedia pages (e.g. "Mary Poppins" -> film vs. character),
        the tag is followed by a parenthetical hint listing the candidates;
        call move_page with the exact target title to disambiguate.

        Returns:
            The content of the current page with permitted links tagged.
        """
        return _wrap_links(game.current_page.content, game.current_page.link_index())

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
        if candidate.lower() == game.current_page.title.lower():
            return (
                f"Move failed: {candidate!r} is the current page. Pick a "
                f"different link to make progress."
            )
        resolution = game.current_page.resolve_link(candidate)
        if resolution is None:
            return (
                f"Move failed: {candidate!r} is not a permitted link from the "
                f"current page ({game.current_page.title!r}). You can only move "
                f"to pages wrapped in <link></link> tags in the content."
            )
        if isinstance(resolution, list):
            options = ", ".join(repr(t) for t in resolution)
            return (
                f"Move failed: {candidate!r} is ambiguous on this page — "
                f"it could mean any of: {options}. Call move_page again with "
                f"one of those exact titles."
            )
        target = resolution
        try:
            new_page = await game.client.get_page(target)
        except WikiClientError as e:
            return f"Move failed: could not load page {target!r}: {e}"

        # MediaWiki redirects can resolve a differently-named link back to the
        # page the agent is already on. Without this check, every such move
        # looks successful; the react/history agents reset state after each
        # success and re-pick the same link, exhausting the message budget.
        if new_page.title.lower() == game.current_page.title.lower():
            return (
                f"Move failed: {candidate!r} redirects to {new_page.title!r}, "
                f"which is the current page. Pick a different link."
            )

        if isinstance(game, WikiGameRules):
            violation = game.violates_rules(new_page)
            if violation:
                return f"Move failed: {violation}"

        await game.move_to(target)
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

        client = game.client
        try:
            cursor = await client.get_page(steps[0])
        except WikiClientError as e:
            return f"Could not load starting page {steps[0]!r}: {e}"

        for i, next_title in enumerate(steps[1:], start=1):
            resolution = cursor.resolve_link(next_title)
            if resolution is None:
                return f"Path breaks at step {i}: {next_title!r} is not a link in {cursor.title!r}."
            if isinstance(resolution, list):
                options = ", ".join(repr(t) for t in resolution)
                return (
                    f"Path is ambiguous at step {i}: {next_title!r} on "
                    f"{cursor.title!r} could mean any of: {options}."
                )
            try:
                cursor = await client.get_page(resolution)
            except WikiClientError as e:
                return f"Could not load page {resolution!r} at step {i}: {e}"

            if cursor.title.lower() == game.goal_page.title.lower():
                return (
                    f"Path is valid and reaches the goal at step {i}: {' -> '.join(steps[: i + 1])}"
                )

        return f"Path is valid for all {len(steps)} steps but does not reach the goal."

    return execute
