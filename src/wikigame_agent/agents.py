"""Wiki-game agents.

Three variants of increasing sophistication:

- `basic_agent`: tool-call loop, resets message history on every successful move
  to keep the context window from growing without bound (the notebook's
  baseline `WikiAgent`).
- `react_agent`: ReAct-style separate reason/act steps each turn.
- `history_agent`: ReAct + retains a compact textual record of prior moves
  across page transitions, instead of throwing the conversation away.
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
from inspect_ai.tool import Tool

from . import prompts
from .game import WikiGame

AgentName = Literal["basic", "react", "history"]


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
    """ReAct: separate reasoning turn, then a tool-call turn."""

    def system() -> ChatMessageSystem:
        return ChatMessageSystem(content=prompts.SYSTEM_REACT)

    async def execute(state: AgentState) -> AgentState:
        state.messages = [system(), _on_page_user(game)]
        while not game.check_win():
            state.messages.append(ChatMessageUser(content=prompts.REASON_PROMPT))
            state.output = await get_model().generate(
                input=state.messages, tools=tools, tool_choice="none"
            )
            state.messages.append(state.output.message)

            state.messages.append(ChatMessageUser(content=prompts.ACT_PROMPT))
            state.output = await get_model().generate(
                input=state.messages, tools=tools, tool_choice="any"
            )
            state.messages.append(state.output.message)

            if state.output.message.tool_calls:
                state = await _run_tool_calls(state, tools)
                if _last_tool_was_successful_move(state):
                    state.messages = [system(), _on_page_user(game)]
        return state

    return execute


@agent
def history_agent(tools: list[Tool], game: WikiGame) -> Agent:
    """ReAct + carries reasoning notes across moves instead of dropping them."""

    def system() -> ChatMessageSystem:
        return ChatMessageSystem(content=prompts.SYSTEM_REACT)

    notes: list[str] = []

    async def execute(state: AgentState) -> AgentState:
        def rebuild() -> list:
            messages = [system(), _on_page_user(game)]
            if notes:
                messages.append(
                    ChatMessageUser(content="Notes from previous moves:\n- " + "\n- ".join(notes))
                )
            return messages

        state.messages = rebuild()
        while not game.check_win():
            state.messages.append(ChatMessageUser(content=prompts.REASON_PROMPT))
            state.output = await get_model().generate(
                input=state.messages, tools=tools, tool_choice="none"
            )
            state.messages.append(state.output.message)
            reasoning = str(state.output.message.content)

            state.messages.append(ChatMessageUser(content=prompts.ACT_PROMPT))
            state.output = await get_model().generate(
                input=state.messages, tools=tools, tool_choice="any"
            )
            state.messages.append(state.output.message)

            if state.output.message.tool_calls:
                state = await _run_tool_calls(state, tools)
                if _last_tool_was_successful_move(state):
                    notes.append(
                        f"On {game.page_history[-2]!r}, reasoned: "
                        f"{_truncate(reasoning, 240)} -> moved to {game.page_history[-1]!r}."
                    )
                    state.messages = rebuild()
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
