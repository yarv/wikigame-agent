from __future__ import annotations

from wikigame_agent.cli import _slug, _task_name


def test_task_name_simple():
    assert _task_name("react", "Apple", "Banana") == "react_Apple_to_Banana"


def test_task_name_handles_spaces_and_punctuation():
    # Wikipedia titles can contain spaces, commas, parens, ampersands, etc.
    name = _task_name("history", "United States", "Coca-Cola (drink)")
    assert name == "history_United-States_to_Coca-Cola-drink"


def test_slug_truncates_overly_long_titles():
    long_title = "A" * 200
    out = _slug(long_title)
    assert len(out) <= 60
    assert out == "A" * 60


def test_slug_returns_placeholder_for_unparseable_input():
    assert _slug("---") == "untitled"
    assert _slug("") == "untitled"
