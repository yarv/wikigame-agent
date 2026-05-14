from __future__ import annotations

from wikigame_agent.game import WikiGame, WikiGameRules
from wikigame_agent.wiki_client import WikiClient


async def test_create_and_check_win(mock_wiki):
    mock_wiki.add_page("A", content="A links to B.", links=["B"])
    mock_wiki.add_page("B", content="B is the goal.", links=[])
    async with WikiClient(user_agent="t") as client:
        game = await WikiGame.create(client, "A", "B")
        assert game.current_page.title == "A"
        assert not game.check_win()
        assert game.is_permitted_link("B")
        await game.move_to("B")
        assert game.check_win()
        assert game.page_history == ["A", "B"]


async def test_move_listener_fires(mock_wiki):
    mock_wiki.add_page("A", content="A links to B.", links=["B"])
    mock_wiki.add_page("B", content="B.", links=[])
    seen: list[tuple[str, str]] = []
    async with WikiClient(user_agent="t") as client:
        game = await WikiGame.create(client, "A", "B")
        game.add_move_listener(lambda g, prev, cur: seen.append((prev.title, cur.title)))
        await game.move_to("B")
    assert seen == [("A", "B")]


async def test_rules_violation_country(mock_wiki):
    mock_wiki.add_page("Start", content="Start links to Canada.", links=["Canada"])
    mock_wiki.add_page(
        "Canada",
        content="Canada is a country in North America. It borders the United States.",
        links=[],
    )
    async with WikiClient(user_agent="t") as client:
        game = await WikiGameRules.create(client, "Start", "Canada", rules=["no countries"])
        assert game.violates_rules(await client.get_page("Canada")) is not None
