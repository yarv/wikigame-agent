from __future__ import annotations

import pytest
import respx
from httpx import Response

from wikigame_agent.wiki_client import (
    WIKIPEDIA_API_URL,
    WikiClient,
    WikiNonJSONResponse,
    WikiPageNotFound,
)


async def test_get_page_returns_content_and_links(mock_wiki):
    mock_wiki.add_page(
        "Canada",
        content="Canada is a country in North America. It borders the United States.",
        links=["North America", "United States"],
    )
    async with WikiClient(user_agent="test-agent") as client:
        page = await client.get_page("Canada")
    assert page.title == "Canada"
    assert "Canada is a country" in page.content
    assert "North America" in page.links
    assert "United States" in page.permitted_links()


async def test_link_index_handles_disambiguated_targets(mock_wiki):
    # MediaWiki's plain-text extract renders the display text ("Mary Poppins"),
    # but the underlying link target is the disambiguated form
    # ("Mary Poppins (film)"). The index must map the bare form found in body
    # to all candidate disambiguated targets.
    mock_wiki.add_page(
        "Saving Mr. Banks",
        content="The film Mary Poppins premiered in 1964. Tangled also.",
        links=["Mary Poppins (film)", "Mary Poppins (character)", "Tangled (2010 film)"],
    )
    async with WikiClient(user_agent="t") as client:
        page = await client.get_page("Saving Mr. Banks")
    index = page.link_index()
    assert set(index["Mary Poppins"]) == {"Mary Poppins (film)", "Mary Poppins (character)"}
    assert index["Tangled"] == ["Tangled (2010 film)"]
    # `permitted_links` exposes the keys for body wrapping.
    assert "Mary Poppins" in page.permitted_links()
    assert "Tangled" in page.permitted_links()


async def test_resolve_link_handles_bare_disambiguated_and_invalid(mock_wiki):
    mock_wiki.add_page(
        "Start",
        content="Discusses Mary Poppins and Tangled.",
        links=["Mary Poppins (film)", "Mary Poppins (character)", "Tangled (2010 film)"],
    )
    async with WikiClient(user_agent="t") as client:
        page = await client.get_page("Start")
    # Unambiguous bare form -> single target.
    assert page.resolve_link("Tangled") == "Tangled (2010 film)"
    # Ambiguous bare form -> list of candidates.
    resolution = page.resolve_link("Mary Poppins")
    assert isinstance(resolution, list)
    assert set(resolution) == {"Mary Poppins (film)", "Mary Poppins (character)"}
    # Direct disambiguated target.
    assert page.resolve_link("Mary Poppins (film)") == "Mary Poppins (film)"
    # Underscore normalization.
    assert page.resolve_link("Tangled_(2010_film)") == "Tangled (2010 film)"
    # Not a link on this page.
    assert page.resolve_link("Walt Disney") is None


async def test_get_page_caches(mock_wiki):
    mock_wiki.add_page("Cache Me", content="hello world.", links=[])
    async with WikiClient(user_agent="test-agent") as client:
        await client.get_page("Cache Me")
        await client.get_page("Cache Me")
        # only one outbound call to MediaWiki
    calls = [c for c in mock_wiki._mock.calls]
    assert len(calls) == 1


async def test_disambiguation_resolves_to_first_link(mock_wiki):
    mock_wiki.add_page(
        "Python",
        content="Python may refer to:",
        links=["Python (programming language)"],
        disambiguation=True,
    )
    mock_wiki.add_page(
        "Python (programming language)",
        content="Python is a high-level programming language.",
        links=[],
    )
    async with WikiClient(user_agent="test-agent") as client:
        page = await client.get_page("Python")
    assert page.title == "Python (programming language)"


async def test_missing_page_with_suggestion(mock_wiki):
    mock_wiki.add_page("Animals", content="Animals are eukaryotic organisms.", links=[])
    async with WikiClient(user_agent="test-agent") as client:
        page = await client.get_page("Animalss")
    assert page.title == "Animals"


async def test_missing_page_with_no_suggestion_raises(mock_wiki):
    async with WikiClient(user_agent="test-agent") as client:
        with pytest.raises(WikiPageNotFound):
            await client.get_page("ZZZ_nonexistent_page")


async def test_non_json_response_is_retried_then_raised():
    """The core fix: an HTML rate-limit page must not crash with JSONDecodeError."""
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(WIKIPEDIA_API_URL).mock(
            return_value=Response(200, text="<html>rate limited</html>")
        )
        async with WikiClient(user_agent="test-agent") as client:
            with pytest.raises(WikiNonJSONResponse):
                await client.get_page("Anything")
        # tenacity retried 5x before reraising
        assert route.call_count == 5


async def test_500_retries_then_succeeds():
    responses = [
        Response(503, text="busy"),
        Response(503, text="busy"),
        Response(
            200,
            json={
                "query": {
                    "pages": [
                        {
                            "pageid": 1,
                            "title": "Eventually",
                            "extract": "ok.",
                            "fullurl": "https://en.wikipedia.org/wiki/Eventually",
                            "links": [],
                        }
                    ]
                }
            },
        ),
    ]
    with respx.mock(assert_all_called=False) as mock:
        mock.get(WIKIPEDIA_API_URL).mock(side_effect=responses)
        async with WikiClient(user_agent="test-agent") as client:
            page = await client.get_page("Eventually")
        assert page.title == "Eventually"


async def test_user_agent_is_sent(mock_wiki):
    mock_wiki.add_page("X", content="x.", links=[])
    async with WikiClient(user_agent="my-agent/1.0 (me@example.com)") as client:
        await client.get_page("X")
    request = mock_wiki._mock.calls[0].request
    assert "my-agent/1.0" in request.headers["user-agent"]
