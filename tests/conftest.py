from __future__ import annotations

from typing import Any

import pytest
import respx
from httpx import Response

from wikigame_agent.wiki_client import WIKIPEDIA_API_URL


def _mw_page_response(
    title: str,
    *,
    content: str,
    links: list[str],
    url: str | None = None,
    pageprops: dict | None = None,
) -> dict[str, Any]:
    return {
        "batchcomplete": True,
        "query": {
            "pages": [
                {
                    "pageid": 1,
                    "ns": 0,
                    "title": title,
                    "extract": content,
                    "fullurl": url or f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                    "links": [{"ns": 0, "title": link} for link in links],
                    **({"pageprops": pageprops} if pageprops else {}),
                }
            ]
        },
    }


@pytest.fixture
def mock_wiki():
    """respx fixture preloaded with a small fake corpus.

    Returns a `Corpus` helper letting individual tests register pages with
    content, outgoing links, and disambiguation/missing flags."""
    with respx.mock(assert_all_called=False, base_url="https://en.wikipedia.org") as mock:
        corpus = _Corpus(mock)
        yield corpus


class _Corpus:
    def __init__(self, mock):
        self._mock = mock
        self._pages: dict[str, dict] = {}
        self._mock.get(WIKIPEDIA_API_URL).mock(side_effect=self._handler)

    def add_page(
        self,
        title: str,
        *,
        content: str,
        links: list[str] | None = None,
        disambiguation: bool = False,
    ) -> None:
        pageprops = {"disambiguation": ""} if disambiguation else None
        self._pages[title.lower()] = _mw_page_response(
            title, content=content, links=links or [], pageprops=pageprops
        )

    def _handler(self, request) -> Response:
        params = dict(request.url.params)
        action = params.get("action")
        if action == "opensearch":
            search = params.get("search", "")
            prefix = search[: min(5, len(search))].lower()
            for title in self._pages:
                if title.startswith(prefix) or search.lower().startswith(title[:5]):
                    return Response(
                        200,
                        json=[search, [self._pages[title]["query"]["pages"][0]["title"]], [], []],
                    )
            return Response(200, json=[search, [], [], []])

        if action == "query":
            titles = params.get("titles", "")
            key = titles.lower()
            if key in self._pages:
                return Response(200, json=self._pages[key])
            return Response(
                200,
                json={"query": {"pages": [{"ns": 0, "title": titles, "missing": True}]}},
            )
        return Response(400, text="unsupported action")
