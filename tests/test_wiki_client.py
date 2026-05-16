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
    # Wikipedia editors use the pipe-trick to render "Mary Poppins" while the
    # link target is "Mary Poppins (film)" etc. The index must map the bare
    # display label found in body anchors to all candidate disambiguated
    # targets.
    body_html = """<div class="mw-parser-output">
        <p>The film <a href="/wiki/Mary_Poppins_(film)">Mary Poppins</a> premiered in 1964.
        <a href="/wiki/Mary_Poppins_(character)">Mary Poppins</a> is the title character.
        Also <a href="/wiki/Tangled_(2010_film)">Tangled</a>.</p>
    </div>"""
    mock_wiki.add_page(
        "Saving Mr. Banks",
        content="The film Mary Poppins premiered in 1964. Tangled also.",
        links=["Mary Poppins (film)", "Mary Poppins (character)", "Tangled (2010 film)"],
        body_html=body_html,
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
    body_html = """<div class="mw-parser-output">
        <p>Discusses <a href="/wiki/Mary_Poppins_(film)">Mary Poppins</a> and
        <a href="/wiki/Mary_Poppins_(character)">Mary Poppins</a> and
        <a href="/wiki/Tangled_(2010_film)">Tangled</a>.</p>
    </div>"""
    mock_wiki.add_page(
        "Start",
        content="Discusses Mary Poppins and Tangled.",
        links=["Mary Poppins (film)", "Mary Poppins (character)", "Tangled (2010 film)"],
        body_html=body_html,
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


async def test_links_inside_infobox_are_not_permitted(mock_wiki):
    # Fairness regression: prop=links lists "Taxonomy" because it's an
    # anchor in the right-rail infobox, and the plain-text extract happens
    # to contain the word "taxonomy" as prose. A human reading the article
    # body cannot click that anchor — so the agent shouldn't be able to
    # either. The new HTML-anchor-based index must exclude it.
    body_html = """<div class="mw-parser-output">
      <table class="infobox biota">
        <tr><th>Scientific classification</th></tr>
        <tr><td><a href="/wiki/Taxonomy_(biology)">Taxonomy</a></td></tr>
        <tr><td><a href="/wiki/Felidae">Felidae</a></td></tr>
      </table>
      <p>The <a href="/wiki/Cat">cat</a> is a small <a href="/wiki/Carnivore">carnivorous</a>
      mammal. Its taxonomy places it in the family Felidae.</p>
    </div>"""
    mock_wiki.add_page(
        "Cat",
        content=(
            "The cat is a small carnivorous mammal. Its taxonomy places it in the family Felidae."
        ),
        links=["Taxonomy (biology)", "Felidae", "Carnivore"],
        body_html=body_html,
    )
    async with WikiClient(user_agent="t") as client:
        page = await client.get_page("Cat")
    permitted = page.permitted_links()
    # Body-prose anchor: allowed.
    assert "carnivorous" in permitted
    # Infobox-only anchors: must NOT be permitted, even though Taxonomy and
    # Felidae both appear in the plain-text extract.
    assert "Taxonomy" not in permitted
    assert "Felidae" not in permitted
    assert page.resolve_link("Taxonomy") is None
    assert page.resolve_link("Felidae") is None


async def test_non_article_namespace_links_are_excluded(mock_wiki):
    body_html = """<div class="mw-parser-output">
      <p>See <a href="/wiki/File:Cat.jpg">image</a>,
      <a href="/wiki/Category:Mammals">Mammals category</a>,
      <a href="/wiki/Template:Taxonomy">template</a>,
      and <a href="/wiki/Real_Page">a real link</a>.</p>
    </div>"""
    mock_wiki.add_page(
        "X",
        content="See image, Mammals, template, and a real link.",
        links=[],
        body_html=body_html,
    )
    async with WikiClient(user_agent="t") as client:
        page = await client.get_page("X")
    permitted = page.permitted_links()
    assert permitted == ["a real link"]


async def test_navbox_and_references_links_are_excluded(mock_wiki):
    body_html = """<div class="mw-parser-output">
      <p>Body has <a href="/wiki/Real_Link">Real</a>.</p>
      <ol class="references">
        <li><a href="/wiki/Footnote_Target">Footnote</a></li>
      </ol>
      <div class="navbox" role="navigation">
        <a href="/wiki/Navbox_Target">NavTarget</a>
      </div>
    </div>"""
    mock_wiki.add_page(
        "Y",
        content="Body has Real. Footnote. NavTarget.",
        links=[],
        body_html=body_html,
    )
    async with WikiClient(user_agent="t") as client:
        page = await client.get_page("Y")
    permitted = page.permitted_links()
    assert "Real" in permitted
    assert "Footnote" not in permitted
    assert "NavTarget" not in permitted


async def test_self_links_are_excluded(mock_wiki):
    body_html = """<div class="mw-parser-output">
      <p>This page is <a href="/wiki/Self">Self</a> and links to
      <a href="/wiki/Other">Other</a>.</p>
    </div>"""
    mock_wiki.add_page(
        "Self",
        content="This page is Self and links to Other.",
        links=[],
        body_html=body_html,
    )
    async with WikiClient(user_agent="t") as client:
        page = await client.get_page("Self")
    assert "Self" not in page.permitted_links()
    assert "Other" in page.permitted_links()


async def test_get_page_caches(mock_wiki):
    mock_wiki.add_page("Cache Me", content="hello world.", links=[])
    async with WikiClient(user_agent="test-agent") as client:
        await client.get_page("Cache Me")
        await client.get_page("Cache Me")
    # First fetch issues two requests (query + parse); the second is served
    # entirely from the in-process page cache.
    actions = [c.request.url.params.get("action") for c in mock_wiki._mock.calls]
    assert actions == ["query", "parse"]


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
    query_success = {
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
    }
    parse_success = {
        "parse": {
            "title": "Eventually",
            "pageid": 1,
            "text": '<div class="mw-parser-output"><p>ok.</p></div>',
        }
    }

    def handler(request):
        # Simulate two 503s on the very first request, then succeed for the
        # query call, then succeed for the subsequent parse call.
        action = request.url.params.get("action")
        if action == "query":
            handler.query_calls += 1
            if handler.query_calls <= 2:
                return Response(503, text="busy")
            return Response(200, json=query_success)
        if action == "parse":
            return Response(200, json=parse_success)
        return Response(400, text="unsupported")

    handler.query_calls = 0

    with respx.mock(assert_all_called=False) as mock:
        mock.get(WIKIPEDIA_API_URL).mock(side_effect=handler)
        async with WikiClient(user_agent="test-agent") as client:
            page = await client.get_page("Eventually")
        assert page.title == "Eventually"


async def test_user_agent_is_sent(mock_wiki):
    mock_wiki.add_page("X", content="x.", links=[])
    async with WikiClient(user_agent="my-agent/1.0 (me@example.com)") as client:
        await client.get_page("X")
    request = mock_wiki._mock.calls[0].request
    assert "my-agent/1.0" in request.headers["user-agent"]
