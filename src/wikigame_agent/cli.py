from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Annotated

import typer
from dotenv import load_dotenv
from inspect_ai import Task, eval_async, task
from inspect_ai.agent import as_solver
from inspect_ai.dataset import Sample

from . import display
from .agents import AGENTS, AgentName
from .config import settings
from .game import Rule, WikiGameRules
from .pricing import register_prices
from .tools import check_path, get_content, move_page
from .wiki_client import WikiClient

load_dotenv()
register_prices()

app = typer.Typer(add_completion=False, help="Wiki Game LLM agent.")


_MAX_TITLE_SLUG = 60


def _slug(text: str) -> str:
    """Filesystem-safe slug for a Wikipedia title (spaces/punct → '-')."""
    cleaned = re.sub(r"[^\w.-]+", "-", text).strip("-")
    if len(cleaned) > _MAX_TITLE_SLUG:
        cleaned = cleaned[:_MAX_TITLE_SLUG].rstrip("-")
    return cleaned or "untitled"


def _task_name(agent_name: str, start: str, goal: str) -> str:
    """Inspect task name used to label log files: `<agent>_<start>_to_<goal>`."""
    return f"{agent_name}_{_slug(start)}_to_{_slug(goal)}"


@app.command()
def play(
    start: Annotated[str, typer.Argument(help="Starting Wikipedia page title.")],
    goal: Annotated[str, typer.Argument(help="Goal Wikipedia page title.")],
    agent: Annotated[AgentName, typer.Option(help="Agent strategy.")] = "react",
    model: Annotated[
        str | None,
        typer.Option(
            help="Inspect model id (e.g. 'openai/gpt-4o-mini'); overrides INSPECT_EVAL_MODEL."
        ),
    ] = None,
    turn_limit: Annotated[
        int,
        typer.Option(
            help="Max number of moves the agent may make before the loop aborts "
            "with reason 'turn_limit'. Counted at the game layer so it means the "
            "same thing across agents (react/history burn different numbers of "
            "messages per move)."
        ),
    ] = 40,
    message_limit: Annotated[
        int,
        typer.Option(
            help="Hard backstop on messages before inspect aborts the run. Kept "
            "high relative to --turn-limit so the turn-based limit fires first."
        ),
    ] = 240,
    enable_check_path: Annotated[
        bool, typer.Option(help="Include the check_path dry-run tool.")
    ] = False,
    reasoning_effort: Annotated[
        str | None,
        typer.Option(
            help="Reasoning effort for o-series / gpt-5 models "
            "(none|minimal|low|medium|high|xhigh|max). Ignored by non-reasoning models. "
            "Defaults to medium because the gpt-5 family's own default is `minimal`, "
            "which leaves react/history agents without enough reasoning to plan."
        ),
    ] = "medium",
    proxy_reasoning: Annotated[
        bool,
        typer.Option(
            help="Split each move turn into a separate text-only reason call "
            "and an act call. Use this for models without native reasoning "
            "(e.g. gpt-4o-mini) or with reasoning_effort=minimal."
        ),
    ] = False,
    log_dir: Annotated[
        str | None,
        typer.Option(help="Where to write inspect logs (default: ./logs)."),
    ] = None,
    no_countries: Annotated[
        bool | None,
        typer.Option(
            "--no-countries/--allow-countries",
            help="Forbid moves onto country articles. Defaults to WIKIGAME_NO_COUNTRIES.",
        ),
    ] = None,
    no_cities: Annotated[
        bool | None,
        typer.Option(
            "--no-cities/--allow-cities",
            help="Forbid moves onto city/town articles. Defaults to WIKIGAME_NO_CITIES.",
        ),
    ] = None,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="DEBUG logging.")] = False,
) -> None:
    """Play the wiki game from START to GOAL."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    chosen_model = model or settings.inspect_eval_model
    os.environ["INSPECT_EVAL_MODEL"] = chosen_model
    chosen_log_dir = log_dir or str(settings.wikigame_log_dir)
    os.makedirs(chosen_log_dir, exist_ok=True)

    rules: list[Rule] = []
    if settings.wikigame_no_countries if no_countries is None else no_countries:
        rules.append("no countries")
    if settings.wikigame_no_cities if no_cities is None else no_cities:
        rules.append("no cities")

    asyncio.run(
        _run(
            start=start,
            goal=goal,
            agent_name=agent,
            model=chosen_model,
            turn_limit=turn_limit,
            message_limit=message_limit,
            enable_check_path=enable_check_path,
            reasoning_effort=reasoning_effort,
            proxy_reasoning=proxy_reasoning,
            log_dir=chosen_log_dir,
            rules=rules,
        )
    )


async def _run(
    *,
    start: str,
    goal: str,
    agent_name: AgentName,
    model: str,
    turn_limit: int,
    message_limit: int,
    enable_check_path: bool,
    reasoning_effort: str | None,
    proxy_reasoning: bool,
    log_dir: str,
    rules: list[Rule],
) -> None:
    async with WikiClient(user_agent=settings.wikigame_user_agent) as client:
        game = await WikiGameRules.create(client, start, goal, rules=rules, turn_limit=turn_limit)
        display.attach(game)
        display.print_banner(
            game, agent_name, model, message_limit, turn_limit=turn_limit, rules=rules
        )

        tools = [get_content(game), move_page(game)]
        if enable_check_path:
            tools.append(check_path(game))

        agent_factory = AGENTS[agent_name]
        solver = as_solver(agent_factory(tools=tools, game=game, proxy_reasoning=proxy_reasoning))

        run_name = _task_name(agent_name, start, goal)

        @task
        def wiki_task() -> Task:
            return Task(
                dataset=[Sample(input="", target="")],
                message_limit=message_limit,
                name=run_name,
            )

        eval_kwargs: dict = {}
        if reasoning_effort is not None:
            eval_kwargs["reasoning_effort"] = reasoning_effort

        # Stay on a single event loop so httpx sockets aren't orphaned when
        # inspect's loop tears down (caused "Event loop is closed" on exit).
        eval_logs = await eval_async(
            wiki_task(),
            solver=solver,
            log_dir=log_dir,
            display="plain",
            **eval_kwargs,
        )

        usage = eval_logs[0].stats.model_usage if eval_logs else None
        display.print_summary(game, usage=usage)


@app.command()
def view(
    log_dir: Annotated[
        str | None,
        typer.Option(help="Inspect log dir to view (default: ./logs)."),
    ] = None,
    port: Annotated[int, typer.Option(help="Port for the inspect viewer.")] = 7575,
) -> None:
    """Launch the inspect log viewer.

    Equivalent to `inspect view --log-dir LOG_DIR --port PORT`."""
    import subprocess

    chosen = log_dir or str(settings.wikigame_log_dir)
    subprocess.run(["inspect", "view", "--log-dir", chosen, "--port", str(port)], check=False)


if __name__ == "__main__":
    app()
