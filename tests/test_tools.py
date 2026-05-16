from __future__ import annotations

from wikigame_agent.game import WikiGame
from wikigame_agent.tools import _wrap_links, check_path, get_content, move_page
from wikigame_agent.wiki_client import WikiClient


def test_wrap_links_marks_first_occurrence():
    content = "Canada borders the United States. The United States is large."
    wrapped = _wrap_links(content, {"United States": ["United States"]})
    # First occurrence wrapped, second untouched.
    assert wrapped.count("<link>United States</link>") == 1
    assert "the United States is large" in wrapped or "The United States is large" in wrapped


def test_wrap_links_longest_first():
    content = "He studied North America and America."
    wrapped = _wrap_links(content, {"America": ["America"], "North America": ["North America"]})
    assert "<link>North America</link>" in wrapped
    # "America" should match the second standalone occurrence, not inside the wrapped one.
    assert wrapped.count("<link>America</link>") == 1


def test_wrap_links_renames_disambiguated_target():
    # Body shows the bare display form; the only target has a parenthetical
    # disambiguator. The agent needs to know the actual target name to click.
    content = "She loved Tangled as a child."
    wrapped = _wrap_links(content, {"Tangled": ["Tangled (2010 film)"]})
    assert "<link>Tangled</link> (links to: Tangled (2010 film))" in wrapped


def test_wrap_links_lists_ambiguous_targets():
    content = "She studied Mary Poppins for years."
    wrapped = _wrap_links(
        content,
        {"Mary Poppins": ["Mary Poppins (film)", "Mary Poppins (character)"]},
    )
    assert "<link>Mary Poppins</link>" in wrapped
    assert "(one of: Mary Poppins (film), Mary Poppins (character))" in wrapped


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


async def test_move_page_rejects_redirect_to_current_page(mock_wiki):
    # Real failure mode observed on gpt-5.4-nano: agent clicked a link whose
    # MediaWiki redirect resolved back to the page it was already on, and
    # repeated this until the message budget ran out. The candidate string
    # differs from the current page so the literal self-link guard misses it;
    # we have to check the resolved title.
    mock_wiki.add_page(
        "Trap",
        content="Trap links to Other and to RedirectsBack.",
        links=["Other", "RedirectsBack"],
    )
    mock_wiki.add_page("Other", content="Other.", links=[])
    # Simulate MediaWiki redirect: looking up "RedirectsBack" returns the Trap
    # page (same payload, canonical title "Trap").
    mock_wiki._pages["redirectsback"] = mock_wiki._pages["trap"]

    async with WikiClient(user_agent="t") as client:
        game = await WikiGame.create(client, "Trap", "Other")
        tool_fn = move_page(game)
        result = await tool_fn(page="RedirectsBack")
        assert "failed" in result.lower()
        assert "redirect" in result.lower()
        assert game.current_page.title == "Trap"
        assert game.page_history == ["Trap"]


async def test_move_page_resolves_bare_form_to_disambiguated_target(mock_wiki):
    # Real failure: on "Saving Mr. Banks", the body says "Mary Poppins" but the
    # underlying link is "Mary Poppins (film)". Pre-fix, the tool refused both
    # the bare form (not in `permitted_links`) and the disambiguated form (not
    # in body); the agent had no way to click through to the goal.
    mock_wiki.add_page(
        "Saving Mr. Banks",
        content="The film Mary Poppins premiered in 1964.",
        links=["Mary Poppins (film)"],
    )
    mock_wiki.add_page("Mary Poppins (film)", content="The 1964 film.", links=[])
    async with WikiClient(user_agent="t") as client:
        game = await WikiGame.create(client, "Saving Mr. Banks", "Mary Poppins (film)")
        tool_fn = move_page(game)
        # Bare form resolves to the disambiguated target.
        result = await tool_fn(page="Mary Poppins")
        assert "successful" in result.lower()
        assert game.check_win()


async def test_move_page_accepts_disambiguated_target_directly(mock_wiki):
    mock_wiki.add_page(
        "Saving Mr. Banks",
        content="The film Mary Poppins premiered in 1964.",
        links=["Mary Poppins (film)"],
    )
    mock_wiki.add_page("Mary Poppins (film)", content="The 1964 film.", links=[])
    async with WikiClient(user_agent="t") as client:
        game = await WikiGame.create(client, "Saving Mr. Banks", "Mary Poppins (film)")
        tool_fn = move_page(game)
        result = await tool_fn(page="Mary Poppins (film)")
        assert "successful" in result.lower()
        assert game.check_win()


async def test_move_page_rejects_ambiguous_bare_click(mock_wiki):
    mock_wiki.add_page(
        "Saving Mr. Banks",
        content="The film Mary Poppins premiered in 1964.",
        links=["Mary Poppins (film)", "Mary Poppins (character)"],
    )
    mock_wiki.add_page("Mary Poppins (film)", content="The 1964 film.", links=[])
    mock_wiki.add_page("Mary Poppins (character)", content="The character.", links=[])
    async with WikiClient(user_agent="t") as client:
        game = await WikiGame.create(client, "Saving Mr. Banks", "Mary Poppins (film)")
        tool_fn = move_page(game)
        result = await tool_fn(page="Mary Poppins")
        assert "ambiguous" in result.lower()
        assert "Mary Poppins (film)" in result
        assert "Mary Poppins (character)" in result
        assert game.current_page.title == "Saving Mr. Banks"


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
