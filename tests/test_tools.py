from __future__ import annotations

from wikigame_agent.game import WikiGame
from wikigame_agent.tools import _wrap_links, check_path, get_content, move_page
from wikigame_agent.wiki_client import WikiClient


def test_wrap_links_marks_first_occurrence():
    content = "Canada borders the United States. The United States is large."
    wrapped = _wrap_links(content, ["United States"])
    # First occurrence wrapped, second untouched.
    assert wrapped.count("<link>United States</link>") == 1
    assert "the United States is large" in wrapped or "The United States is large" in wrapped


def test_wrap_links_longest_first():
    content = "He studied North America and America."
    wrapped = _wrap_links(content, ["America", "North America"])
    assert "<link>North America</link>" in wrapped
    # "America" should match the second standalone occurrence, not inside the wrapped one.
    assert wrapped.count("<link>America</link>") == 1


async def test_get_content_tool_returns_tagged(mock_wiki):
    mock_wiki.add_page("Start", content="Start mentions Other. End.", links=["Other"])
    mock_wiki.add_page("Other", content="Other.", links=[])
    async with WikiClient(user_agent="t") as client:
        game = await WikiGame.create(client, "Start", "Other")
        tool_fn = get_content(game)
        out = await tool_fn()
        assert "<link>Other</link>" in out


async def test_move_page_tool_success_and_failure(mock_wiki):
    mock_wiki.add_page(
        "Start",
        content="Start links to Allowed and nothing else.",
        links=["Allowed", "Disallowed"],
    )
    mock_wiki.add_page("Allowed", content="Allowed.", links=[])
    mock_wiki.add_page("Disallowed", content="Disallowed.", links=[])
    async with WikiClient(user_agent="t") as client:
        game = await WikiGame.create(client, "Start", "Allowed")
        tool_fn = move_page(game)
        bad = await tool_fn(page="Disallowed")
        assert "failed" in bad.lower()
        good = await tool_fn(page="Allowed")
        assert "successful" in good.lower()
        assert game.check_win()


async def test_move_page_rejects_self_link(mock_wiki):
    # A self-link previously let the agent "move" to its own page and oscillate
    # (see CLAUDE.md: gpt-5.4-mini self-looped on "Transvestic disorder").
    mock_wiki.add_page(
        "Loop",
        content="Loop links to Loop and to Other.",
        links=["Loop", "Other"],
    )
    mock_wiki.add_page("Other", content="Other.", links=[])
    async with WikiClient(user_agent="t") as client:
        game = await WikiGame.create(client, "Loop", "Other")
        tool_fn = move_page(game)
        result = await tool_fn(page="Loop")
        assert "failed" in result.lower()
        assert game.current_page.title == "Loop"
        assert game.page_history == ["Loop"]


async def test_check_path_tool(mock_wiki):
    mock_wiki.add_page("A", content="A links to B.", links=["B"])
    mock_wiki.add_page("B", content="B links to C.", links=["C"])
    mock_wiki.add_page("C", content="C is goal.", links=[])
    async with WikiClient(user_agent="t") as client:
        game = await WikiGame.create(client, "A", "C")
        fn = check_path(game)
        good = await fn(path="A -> B -> C")
        assert "reaches the goal" in good.lower()
        broken = await fn(path="A -> C")
        assert "breaks" in broken.lower()
