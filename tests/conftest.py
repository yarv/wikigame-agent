from __future__ import annotations

import html
from typing import Any

import pytest
import respx
from httpx import Response

from wikigame_agent.wiki_client import WIKIPEDIA_API_URL


def _default_body_html(content: str, links: list[str]) -> str:
    """Synthesize a minimal article-body HTML for tests.

    The plain content is rendered as a `<p>` and each `links` entry becomes
    a `<p><a href="/wiki/Target">Target</a></p>` anchor — i.e. display text
    == target title. Tests that need pipe-trick or chrome-nested anchors
    must pass `body_html=` explicitly.
    """
    parts = ['<div class="mw-parser-output"><p>', html.escape(content), "</p>"]
    for target in links:
        href = "/wiki/" + target.replace(" ", "_")
        parts.append(f'<p><a href="{html.escape(href, quote=True)}">{html.escape(target)}</a></p>')
    parts.append("</div>")
    return "".join(parts)


def _mw_query_response(
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


def _mw_parse_response(title: str, body_html: str) -> dict[str, Any]:
    return {
        "parse": {
            "title": title,
            "pageid": 1,
            "text": body_html,
        }
    }


@pytest.fixture
def mock_wiki():
    """respx fixture preloaded with a small fake corpus.

    Returns a `Corpus` helper letting individual tests register pages with
    content, outgoing links, and disambiguation/missing flags. Each page
    serves both an `action=query` response (extract + prop=links) and an
    `action=parse` response (rendered body HTML) — the client needs both to
    construct a WikiPage."""
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
        body_html: str | None = None,
        disambiguation: bool = False,
    ) -> None:
        links = links or []
        pageprops = {"disambiguation": ""} if disambiguation else None
        if body_html is None:
            body_html = _default_body_html(content, links)
        self._pages[title.lower()] = {
            "title": title,
            "query": _mw_query_response(title, content=content, links=links, pageprops=pageprops),
            "parse": _mw_parse_response(title, body_html),
        }

    def _handler(self, request) -> Response:
        params = dict(request.url.params)
        action = params.get("action")
        if action == "opensearch":
            search = params.get("search", "")
            prefix = search[: min(5, len(search))].lower()
            for title, entry in self._pages.items():
                if title.startswith(prefix) or search.lower().startswith(title[:5]):
                    return Response(
                        200,
                        json=[search, [entry["title"]], [], []],
                    )
            return Response(200, json=[search, [], [], []])

        if action == "query":
            titles = params.get("titles", "")
            key = titles.lower()
            if key in self._pages:
                return Response(200, json=self._pages[key]["query"])
            return Response(
                200,
                json={"query": {"pages": [{"ns": 0, "title": titles, "missing": True}]}},
            )

        if action == "parse":
            page = params.get("page", "")
            key = page.lower()
            if key in self._pages:
                return Response(200, json=self._pages[key]["parse"])
            return Response(200, json=_mw_parse_response(page, ""))

        return Response(400, text="unsupported action")
