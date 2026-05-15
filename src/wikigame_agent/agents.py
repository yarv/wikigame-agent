"""Wiki-game agents.

Three variants of increasing sophistication:

- `basic_agent`: tool-call loop, resets message history on every successful move
  to keep the context window from growing without bound (the notebook's
  baseline `WikiAgent`).
- `react_agent`: one model call per turn, alternating a forced `get_content`
  on each new page with a `move_page` call (reasoning + tool call in a single
  response).
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
from .game import WikiGame

AgentName = Literal["basic", "react", "history"]

_Mode = Literal["fetch", "move"]
_GET_CONTENT = "get_content"


def _on_page_user(game: WikiGame) -> ChatMessageUser:
    return ChatMessageUser(content=prompts.on_page(game))


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


def _turn_config(
    mode: _Mode, fetch_tools: list[Tool], move_tools: list[Tool]
) -> tuple[list[Tool], ToolChoice]:
    if mode == "fetch":
        return fetch_tools, ToolFunction(name=_GET_CONTENT)
    return move_tools, "any"


@agent
def basic_agent(tools: list[Tool], game: WikiGame) -> Agent:
    """Baseline: think → act → if moved, reset history; loop until win."""

    def system() -> ChatMessageSystem:
        return ChatMessageSystem(content=prompts.SYSTEM_BASIC)

    async def execute(state: AgentState) -> AgentState:
        state.messages = [system(), _on_page_user(game)]
        while not game.check_win():
            state.messages.append(ChatMessageUser(content=prompts.NEXT_STEP))
            state.output = await get_model().generate(input=state.messages, tools=tools)
            state.messages.append(state.output.message)
            if state.output.message.tool_calls:
                state = await _run_tool_calls(state, tools)
                if _last_tool_was_successful_move(state):
                    state.messages = [system(), _on_page_user(game)]
        return state

    return execute


@agent
def react_agent(tools: list[Tool], game: WikiGame) -> Agent:
    """ReAct: one model call per turn. After arriving on a new page, the model
    is forced to call `get_content`; from then on it is free to call any
    move-phase tool (reasoning text and the tool call come back in one response)
    until the move succeeds, at which point the conversation resets."""

    fetch_tools, move_tools = _partition_tools(tools)

    def system() -> ChatMessageSystem:
        return ChatMessageSystem(content=prompts.SYSTEM_REACT)

    async def execute(state: AgentState) -> AgentState:
        state.messages = [system(), _on_page_user(game)]
        mode: _Mode = "fetch"
        while not game.check_win():
            state.messages.append(ChatMessageUser(content=prompts.STEP_PROMPT))
            turn_tools, turn_choice = _turn_config(mode, fetch_tools, move_tools)
            state.output = await get_model().generate(
                input=state.messages, tools=turn_tools, tool_choice=turn_choice
            )
            state.messages.append(state.output.message)
            if state.output.message.tool_calls:
                state = await _run_tool_calls(state, tools)
                if mode == "fetch":
                    mode = "move"
                elif _last_tool_was_successful_move(state):
                    state.messages = [system(), _on_page_user(game)]
                    mode = "fetch"
        return state

    return execute


@agent
def history_agent(tools: list[Tool], game: WikiGame) -> Agent:
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
        while not game.check_win():
            state.messages.append(ChatMessageUser(content=prompts.STEP_PROMPT))
            turn_tools, turn_choice = _turn_config(mode, fetch_tools, move_tools)
            state.output = await get_model().generate(
                input=state.messages, tools=turn_tools, tool_choice=turn_choice
            )
            state.messages.append(state.output.message)
            if mode == "move":
                move_reasoning = str(state.output.message.content)
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
        return state

    return execute


def _truncate(s: str, max_len: int) -> str:
    s = s.strip().replace("\n", " ")
    return s if len(s) <= max_len else s[: max_len - 1] + "…"


AGENTS: dict[AgentName, Agent] = {
    "basic": basic_agent,
    "react": react_agent,
    "history": history_agent,
}
