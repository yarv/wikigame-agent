"""Wiki-game agents.

Two variants:

- `react_agent`: one model call per turn, alternating a forced `get_content`
  on each new page with a `move_page` call (reasoning + tool call in a single
  response). With `proxy_reasoning=True` the move turn splits into a separate
  text-only reason call followed by the act call — useful for models without
  native reasoning (e.g. gpt-4o-mini) or with reasoning turned off.
- `history_agent`: `react_agent` + retains a compact textual record of prior
  moves across page transitions, instead of throwing the conversation away.
"""

from __future__ import annotations

from typing import Literal

from inspect_ai.agent import Agent, AgentState, agent
from inspect_ai.model import (
    ChatMessageSystem,
    ChatMessageUser,
    execute_tools,
    get_model,
)
from inspect_ai.tool import Tool, ToolChoice, ToolDef, ToolFunction

from . import prompts
from .game import WikiGame, WikiGameRules

AgentName = Literal["react", "history"]

_Mode = Literal["fetch", "move"]
_GET_CONTENT = "get_content"


def _on_page_user(game: WikiGame) -> ChatMessageUser:
    rules = game.rules if isinstance(game, WikiGameRules) else None
    return ChatMessageUser(content=prompts.on_page(game, rules=rules))


async def _run_tool_calls(state: AgentState, tools: list[Tool]) -> AgentState:
    result = await execute_tools(messages=state.messages, tools=tools)
    state.messages.extend(result.messages)
    state.output = result.output
    return state


def _last_tool_was_successful_move(state: AgentState) -> bool:
    # Look at the most recent tool messages.
    for msg in reversed(state.messages):
        if msg.role == "tool":
            content = str(msg.content).lower()
            return content.startswith("move successful")
    return False


def _detected_cycle(page_history: list[str]) -> bool:
    """Return True if the tail of `page_history` forms a tight repeating loop.

    Catches the two traps we've seen in practice:

    - **A ↔ B oscillation** — the last 4 entries are `[A, B, A, B]`.
    - **A → B → C → A short cycle** — the last 4 entries return to a recent
      page (`[A, B, C, A]` with B and C both distinct from A).

    Anything longer than that is left to the message/turn budget. Old repeats
    in the middle of the path don't trigger — we only look at the tail.
    """
    n = len(page_history)
    if n < 4:
        return False
    a, b, c, d = page_history[-4], page_history[-3], page_history[-2], page_history[-1]
    # A ↔ B oscillation.
    if a == c and b == d and a != b:
        return True
    # A → B → C → A short cycle (returns to a page from 3 moves ago).
    return a == d and b != a and c != a and b != c


def _cycle_pages(page_history: list[str]) -> list[str]:
    """Pages involved in the most recent cycle, in the order they appear in
    the tail. Used to render the nudge message."""
    seen: list[str] = []
    for title in page_history[-4:]:
        if title not in seen:
            seen.append(title)
    return seen


def _partition_tools(tools: list[Tool]) -> tuple[list[Tool], list[Tool]]:
    """Split tools into (fetch_tools, move_tools).

    Fetch phase exposes only `get_content`; the move phase exposes everything
    else (typically `move_page`, optionally `check_path`)."""
    fetch_tools: list[Tool] = []
    move_tools: list[Tool] = []
    for t in tools:
        name = ToolDef(t).name
        if name == _GET_CONTENT:
            fetch_tools.append(t)
        else:
            move_tools.append(t)
    if not fetch_tools:
        raise ValueError(f"react/history agents require a {_GET_CONTENT!r} tool")
    if not move_tools:
        raise ValueError("react/history agents require at least one move-phase tool")
    return fetch_tools, move_tools


async def _do_fetch_turn(state: AgentState, fetch_tools: list[Tool]) -> None:
    """Single model call, forced to call `get_content`."""
    state.messages.append(ChatMessageUser(content=prompts.STEP_PROMPT))
    state.output = await get_model().generate(
        input=state.messages,
        tools=fetch_tools,
        tool_choice=ToolFunction(name=_GET_CONTENT),
    )
    state.messages.append(state.output.message)


async def _do_move_turn(state: AgentState, move_tools: list[Tool], *, proxy_reasoning: bool) -> str:
    """Run a move turn. Returns the reasoning text produced (may be empty).

    With `proxy_reasoning=False`, a single call asks the model to reason and
    act in one response — relies on the model reasoning internally (o-series,
    gpt-5 with `reasoning_effort` set) or emitting CoT alongside the tool call.

    With `proxy_reasoning=True`, splits into a `tool_choice="none"` reason call
    (forces visible reasoning text) followed by a `tool_choice="any"` act call
    — needed for models that don't reason natively, e.g. gpt-4o-mini.
    """
    if proxy_reasoning:
        state.messages.append(ChatMessageUser(content=prompts.REASON_PROMPT))
        state.output = await get_model().generate(
            input=state.messages, tools=move_tools, tool_choice="none"
        )
        state.messages.append(state.output.message)
        reasoning = str(state.output.message.content)

        state.messages.append(ChatMessageUser(content=prompts.ACT_PROMPT))
        state.output = await get_model().generate(
            input=state.messages, tools=move_tools, tool_choice="any"
        )
        state.messages.append(state.output.message)
        return reasoning

    state.messages.append(ChatMessageUser(content=prompts.STEP_PROMPT))
    turn_choice: ToolChoice = "any"
    state.output = await get_model().generate(
        input=state.messages, tools=move_tools, tool_choice=turn_choice
    )
    state.messages.append(state.output.message)
    return str(state.output.message.content)


@agent
def react_agent(tools: list[Tool], game: WikiGame, *, proxy_reasoning: bool = False) -> Agent:
    """ReAct with a forced fetch-then-move alternation."""

    fetch_tools, move_tools = _partition_tools(tools)

    def system() -> ChatMessageSystem:
        return ChatMessageSystem(content=prompts.SYSTEM_REACT)

    async def execute(state: AgentState) -> AgentState:
        state.messages = [system(), _on_page_user(game)]
        mode: _Mode = "fetch"
        cycle_strikes = 0
        while not game.check_win():
            if game.turn_limit_reached():
                game.termination_reason = "turn_limit"
                break
            if mode == "fetch":
                await _do_fetch_turn(state, fetch_tools)
            else:
                await _do_move_turn(state, move_tools, proxy_reasoning=proxy_reasoning)
            if state.output.message.tool_calls:
                state = await _run_tool_calls(state, tools)
                if mode == "fetch":
                    mode = "move"
                elif _last_tool_was_successful_move(state):
                    state.messages = [system(), _on_page_user(game)]
                    mode = "fetch"
                    if _detected_cycle(game.page_history):
                        cycle_strikes += 1
                        if cycle_strikes >= 2:
                            game.termination_reason = "cycle"
                            break
                        state.messages.append(
                            ChatMessageUser(
                                content=prompts.cycle_nudge(_cycle_pages(game.page_history))
                            )
                        )
        return state

    return execute


@agent
def history_agent(tools: list[Tool], game: WikiGame, *, proxy_reasoning: bool = False) -> Agent:
    """`react_agent` + carries reasoning notes across moves instead of dropping them."""

    fetch_tools, move_tools = _partition_tools(tools)
    notes: list[str] = []

    def system() -> ChatMessageSystem:
        return ChatMessageSystem(content=prompts.SYSTEM_REACT)

    async def execute(state: AgentState) -> AgentState:
        def rebuild() -> list:
            messages = [system(), _on_page_user(game)]
            if notes:
                messages.append(
                    ChatMessageUser(content="Notes from previous moves:\n- " + "\n- ".join(notes))
                )
            return messages

        state.messages = rebuild()
        mode: _Mode = "fetch"
        move_reasoning = ""
        cycle_strikes = 0
        while not game.check_win():
            if game.turn_limit_reached():
                game.termination_reason = "turn_limit"
                break
            if mode == "fetch":
                await _do_fetch_turn(state, fetch_tools)
            else:
                move_reasoning = await _do_move_turn(
                    state, move_tools, proxy_reasoning=proxy_reasoning
                )
            if state.output.message.tool_calls:
                state = await _run_tool_calls(state, tools)
                if mode == "fetch":
                    mode = "move"
                elif _last_tool_was_successful_move(state):
                    notes.append(
                        f"On {game.page_history[-2]!r}, reasoned: "
                        f"{_truncate(move_reasoning, 240)} -> moved to {game.page_history[-1]!r}."
                    )
                    state.messages = rebuild()
                    mode = "fetch"
                    if _detected_cycle(game.page_history):
                        cycle_strikes += 1
                        if cycle_strikes >= 2:
                            game.termination_reason = "cycle"
                            break
                        state.messages.append(
                            ChatMessageUser(
                                content=prompts.cycle_nudge(_cycle_pages(game.page_history))
                            )
                        )
        return state

    return execute


def _truncate(s: str, max_len: int) -> str:
    s = s.strip().replace("\n", " ")
    return s if len(s) <= max_len else s[: max_len - 1] + "…"


AGENTS: dict[AgentName, Agent] = {
    "react": react_agent,
    "history": history_agent,
}
