"""Tests for the parts of `agents.py` that don't require a live model.

The agents themselves run an inspect_ai model loop; exercising that end-to-end
needs a mock LLM provider and is left for an integration test. The pure-function
helpers (`_partition_tools`, `_last_tool_was_successful_move`, `_truncate`)
encode the load-bearing invariants of the react/history loop, so they're worth
covering directly.
"""

from __future__ import annotations

import pytest
from inspect_ai.agent import AgentState
from inspect_ai.model import ChatMessageTool, ChatMessageUser

from wikigame_agent.agents import (
    _cycle_pages,
    _detected_cycle,
    _last_tool_was_successful_move,
    _partition_tools,
    _truncate,
)
from wikigame_agent.game import WikiGame
from wikigame_agent.prompts import cycle_nudge
from wikigame_agent.tools import check_path, get_content, move_page
from wikigame_agent.wiki_client import WikiClient


async def _game(mock_wiki) -> tuple[WikiClient, WikiGame]:
    mock_wiki.add_page("Start", content="Start links to Goal.", links=["Goal"])
    mock_wiki.add_page("Goal", content="Goal.", links=[])
    client = WikiClient(user_agent="t")
    await client.__aenter__()
    game = await WikiGame.create(client, "Start", "Goal")
    return client, game


async def test_partition_tools_splits_get_content_from_move(mock_wiki):
    client, game = await _game(mock_wiki)
    try:
        tools = [get_content(game), move_page(game), check_path(game)]
        fetch_tools, move_tools = _partition_tools(tools)
        assert len(fetch_tools) == 1
        assert len(move_tools) == 2
    finally:
        await client.__aexit__(None, None, None)


async def test_partition_tools_requires_get_content(mock_wiki):
    client, game = await _game(mock_wiki)
    try:
        with pytest.raises(ValueError, match="get_content"):
            _partition_tools([move_page(game)])
    finally:
        await client.__aexit__(None, None, None)


async def test_partition_tools_requires_a_move_tool(mock_wiki):
    client, game = await _game(mock_wiki)
    try:
        with pytest.raises(ValueError, match="move-phase tool"):
            _partition_tools([get_content(game)])
    finally:
        await client.__aexit__(None, None, None)


def test_last_tool_was_successful_move_detects_success():
    state = AgentState(
        messages=[
            ChatMessageUser(content="hi"),
            ChatMessageTool(
                tool_call_id="1",
                content="Move successful. You are now on 'Goal'.",
            ),
        ]
    )
    assert _last_tool_was_successful_move(state) is True


def test_last_tool_was_successful_move_detects_failure():
    state = AgentState(
        messages=[
            ChatMessageTool(
                tool_call_id="1",
                content="Move failed: 'X' is not a permitted link.",
            ),
        ]
    )
    assert _last_tool_was_successful_move(state) is False


def test_last_tool_was_successful_move_ignores_earlier_tool_messages():
    """Only the *most recent* tool message matters — earlier successful moves
    that happened before a later failed move must not return True."""
    state = AgentState(
        messages=[
            ChatMessageTool(tool_call_id="1", content="Move successful."),
            ChatMessageUser(content="next turn"),
            ChatMessageTool(tool_call_id="2", content="Move failed: nope."),
        ]
    )
    assert _last_tool_was_successful_move(state) is False


def test_last_tool_was_successful_move_no_tool_messages():
    state = AgentState(messages=[ChatMessageUser(content="hi")])
    assert _last_tool_was_successful_move(state) is False


def test_truncate_short_string_unchanged():
    assert _truncate("hello", 100) == "hello"


def test_truncate_long_string_uses_ellipsis():
    out = _truncate("a" * 50, 10)
    assert len(out) == 10
    assert out.endswith("…")


def test_truncate_strips_and_flattens_newlines():
    out = _truncate("  line one\nline two  ", 100)
    assert out == "line one line two"


# --- cycle detection ---------------------------------------------------------


def test_detected_cycle_ab_oscillation():
    assert _detected_cycle(["Start", "A", "B", "A", "B"]) is True


def test_detected_cycle_abc_returns_to_a():
    assert _detected_cycle(["Start", "A", "B", "C", "A"]) is True


def test_detected_cycle_no_cycle_returns_false():
    assert _detected_cycle(["Start", "A", "B", "C", "D"]) is False


def test_detected_cycle_short_history_returns_false():
    # Need at least 4 entries for any cycle check to fire.
    assert _detected_cycle([]) is False
    assert _detected_cycle(["A"]) is False
    assert _detected_cycle(["A", "B"]) is False
    assert _detected_cycle(["A", "B", "A"]) is False


def test_detected_cycle_old_repeat_in_middle_does_not_trigger():
    """A repeat that's not in the tail-of-4 must not trigger — we only catch
    *tight* recent loops, not any prior revisit."""
    history = ["A", "B", "A", "C", "D", "E", "F"]
    assert _detected_cycle(history) is False


def test_detected_cycle_three_in_a_row_same_page_is_not_a_cycle():
    """Sanity: the move tool prevents staying put, but if a malformed
    history somehow had a self-loop the cycle detector should treat it as
    pathological rather than the A↔B pattern."""
    assert _detected_cycle(["A", "A", "A", "A"]) is False


def test_cycle_pages_dedupes_in_order_two_pages():
    assert _cycle_pages(["Start", "A", "B", "A", "B"]) == ["A", "B"]


def test_cycle_pages_dedupes_in_order_three_pages():
    assert _cycle_pages(["Start", "A", "B", "C", "A"]) == ["A", "B", "C"]


def test_cycle_nudge_two_pages_uses_and():
    msg = cycle_nudge(["Persuasion", "Rhetoric"])
    assert "'Persuasion' and 'Rhetoric'" in msg
    assert "cycling between" in msg


def test_cycle_nudge_three_pages_uses_comma_and():
    msg = cycle_nudge(["A", "B", "C"])
    assert "'A', 'B', and 'C'" in msg
