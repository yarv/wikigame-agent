from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from inspect_ai.model import ModelUsage
from rich.console import Console

from wikigame_agent import display
from wikigame_agent.wiki_client import WikiPage


class _FakeGame:
    def __init__(self) -> None:
        self.page_history = ["Start", "Mid", "Goal"]
        self.goal_page = WikiPage(title="Goal", url="", content="", summary="", links=())

    def check_win(self) -> bool:
        return self.page_history[-1] == self.goal_page.title


def _capture_summary(game, usage=None) -> str:
    buf = StringIO()
    fake_console = Console(file=buf, force_terminal=False, width=120)
    with patch.object(display, "console", fake_console):
        display.print_summary(game, usage=usage)
    return buf.getvalue()


def test_summary_without_usage_omits_token_and_cost_lines():
    out = _capture_summary(_FakeGame())
    assert "Tokens:" not in out
    assert "Cost:" not in out


def test_summary_with_usage_shows_tokens_and_cost():
    usage = {
        "anthropic/claude-haiku-4-5": ModelUsage(
            input_tokens=1_200,
            output_tokens=340,
            total_tokens=1_540,
            input_tokens_cache_read=100,
            total_cost=0.0123,
        )
    }
    out = _capture_summary(_FakeGame(), usage=usage)
    assert "1,540" in out
    assert "in 1,200" in out
    assert "out 340" in out
    assert "cache 100" in out
    assert "$0.0123" in out


def test_summary_rolls_up_multiple_models():
    usage = {
        "openai/gpt-4o-mini": ModelUsage(
            input_tokens=100, output_tokens=50, total_tokens=150, total_cost=0.001
        ),
        "anthropic/claude-haiku-4-5": ModelUsage(
            input_tokens=200, output_tokens=70, total_tokens=270, total_cost=0.002
        ),
    }
    out = _capture_summary(_FakeGame(), usage=usage)
    # 420 = 100+50+200+70
    assert "420" in out
    assert "$0.0030" in out


def test_summary_shows_em_dash_when_cost_unknown():
    usage = {
        "fake/unknown": ModelUsage(
            input_tokens=10, output_tokens=5, total_tokens=15, total_cost=None
        )
    }
    out = _capture_summary(_FakeGame(), usage=usage)
    assert "—" in out
    assert "not in pricing data" in out
