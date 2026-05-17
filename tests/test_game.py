from __future__ import annotations

from wikigame_agent.game import WikiGame, WikiGameRules
from wikigame_agent.prompts import on_page
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


async def test_rules_violation_city(mock_wiki):
    mock_wiki.add_page("Start", content="Start links to Paris.", links=["Paris"])
    mock_wiki.add_page(
        "Paris",
        content="Paris is the capital of France and a major European city.",
        links=[],
    )
    async with WikiClient(user_agent="t") as client:
        game = await WikiGameRules.create(client, "Start", "Paris", rules=["no cities"])
        violation = game.violates_rules(await client.get_page("Paris"))
        assert violation is not None
        assert "city" in violation


async def test_on_page_surfaces_active_rules(mock_wiki):
    mock_wiki.add_page("Start", content="Start.", links=[])
    mock_wiki.add_page("Goal", content="Goal.", links=[])
    async with WikiClient(user_agent="t") as client:
        plain = await WikiGame.create(client, "Start", "Goal")
        assert "Rules in effect" not in on_page(plain)

        ruled = await WikiGameRules.create(
            client, "Start", "Goal", rules=["no countries", "no cities"]
        )
        text = on_page(ruled, rules=ruled.rules)
        assert "Rules in effect" in text
        assert "no countries" in text
        assert "no cities" in text


async def test_rules_no_cities_does_not_block_countries(mock_wiki):
    mock_wiki.add_page("Start", content="Start links to Canada.", links=["Canada"])
    mock_wiki.add_page(
        "Canada",
        content="Canada is a country in North America.",
        links=[],
    )
    async with WikiClient(user_agent="t") as client:
        game = await WikiGameRules.create(client, "Start", "Canada", rules=["no cities"])
        assert game.violates_rules(await client.get_page("Canada")) is None


async def test_turn_limit_unset_is_never_reached(mock_wiki):
    mock_wiki.add_page("A", content="A links to B.", links=["B"])
    mock_wiki.add_page("B", content="B links to C.", links=["C"])
    mock_wiki.add_page("C", content="C.", links=[])
    async with WikiClient(user_agent="t") as client:
        game = await WikiGame.create(client, "A", "C")
        assert game.turn_limit is None
        assert game.turn_limit_reached() is False
        await game.move_to("B")
        assert game.turn_limit_reached() is False


async def test_turn_limit_reached_when_moves_equal_limit(mock_wiki):
    mock_wiki.add_page("A", content="A links to B.", links=["B"])
    mock_wiki.add_page("B", content="B links to C.", links=["C"])
    mock_wiki.add_page("C", content="C.", links=[])
    async with WikiClient(user_agent="t") as client:
        game = await WikiGame.create(client, "A", "C", turn_limit=2)
        assert game.turn_limit_reached() is False  # 0 moves
        await game.move_to("B")
        assert game.turn_limit_reached() is False  # 1 move
        await game.move_to("C")
        assert game.turn_limit_reached() is True  # 2 moves, at limit


async def test_turn_limit_reached_when_overshot(mock_wiki):
    mock_wiki.add_page("A", content="A links to B.", links=["B"])
    mock_wiki.add_page("B", content="B links to A.", links=["A"])
    async with WikiClient(user_agent="t") as client:
        game = await WikiGame.create(client, "A", "B", turn_limit=1)
        await game.move_to("B")  # 1 move, at limit
        await game.move_to("A")  # 2 moves, past limit
        assert game.turn_limit_reached() is True


async def test_check_win_sets_termination_reason(mock_wiki):
    mock_wiki.add_page("A", content="A links to B.", links=["B"])
    mock_wiki.add_page("B", content="B.", links=[])
    async with WikiClient(user_agent="t") as client:
        game = await WikiGame.create(client, "A", "B")
        assert game.termination_reason is None
        await game.move_to("B")
        assert game.check_win() is True
        assert game.termination_reason == "reached_goal"


async def test_rules_create_passes_turn_limit(mock_wiki):
    mock_wiki.add_page("Start", content="Start.", links=[])
    mock_wiki.add_page("Goal", content="Goal.", links=[])
    async with WikiClient(user_agent="t") as client:
        game = await WikiGameRules.create(
            client, "Start", "Goal", rules=["no cities"], turn_limit=5
        )
        assert game.turn_limit == 5
        assert game.rules == ["no cities"]
