"""Async MediaWiki client.

Why this exists: the `wikipedia` PyPI package is unmaintained, sends no
User-Agent, has no retry/backoff, and parses MediaWiki responses fragilely.
When Wikipedia rate-limits or returns an HTML error page, the package tries to
`json.loads` it and crashes with `JSONDecodeError`. This client fixes that by:

- setting a real User-Agent (Wikipedia's API etiquette requires it and
  silently rate-limits clients that don't)
- retrying on transient HTTP errors with exponential backoff
- raising a clear error when a response isn't JSON, instead of crashing deep
  in a parser
- caching pages in-process so a single game doesn't re-fetch the same page
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"


class WikiClientError(Exception):
    """Base class for wiki client errors."""


class WikiPageNotFound(WikiClientError):
    """Raised when a page cannot be found, even after redirect / suggestion."""


class WikiNonJSONResponse(WikiClientError):
    """Raised when the MediaWiki API returns a non-JSON body (usually an HTML
    rate-limit or error page). Retried by the client."""


_DISAMBIGUATOR_RE = re.compile(r"\s*\([^)]+\)\s*$")


def _strip_disambiguator(title: str) -> str:
    """`"Mary Poppins (film)"` -> `"Mary Poppins"`."""
    return _DISAMBIGUATOR_RE.sub("", title).strip()


@dataclass(frozen=True)
class WikiPage:
    title: str
    url: str
    content: str
    summary: str
    links: tuple[str, ...]

    def link_index(self) -> dict[str, list[str]]:
        """Display form -> list of target page titles, for body-visible links.

        Mirrors the original notebook's "main content" heuristic, with two
        extensions: (1) a link whose target has a parenthetical disambiguator
        (e.g. ``"Mary Poppins (film)"``) is included if the bare form
        (``"Mary Poppins"``) appears in the body — Wikipedia's plain-text
        extract renders the display text, not the wikitext target; (2) a
        single bare display form may map to multiple disambiguated targets
        (``"Mary Poppins" -> ["Mary Poppins (film)", "Mary Poppins (character)"]``),
        and the caller decides how to surface the ambiguity. Self-links are
        excluded.
        """
        content_lower = self.content.lower()
        title_lower = self.title.lower()
        index: dict[str, list[str]] = {}
        for link in self.links:
            if link.lower() == title_lower:
                continue
            forms: list[str] = []
            if link.lower() in content_lower:
                forms.append(link)
            bare = _strip_disambiguator(link)
            if bare and bare.lower() != link.lower() and bare.lower() in content_lower:
                forms.append(bare)
            for form in forms:
                bucket = index.setdefault(form, [])
                if link not in bucket:
                    bucket.append(link)
        return index

    def permitted_links(self) -> list[str]:
        """Display forms agents can click. See :meth:`link_index`."""
        return list(self.link_index().keys())

    def resolve_link(self, candidate: str) -> str | list[str] | None:
        """Map a click candidate to the target page title to fetch.

        Returns:
            - ``str``: the target title (unambiguous click).
            - ``list[str]``: candidate targets, when ``candidate`` is a bare
              display form that maps to multiple disambiguated targets.
            - ``None``: ``candidate`` is not a valid move from this page.

        Accepts either a body-visible display form (``"Mary Poppins"``) or
        a disambiguated target name (``"Mary Poppins (film)"``) — the latter
        is needed because the disambiguation hint shown to the agent lists
        target names, and the agent will click those directly.
        """
        normalized = candidate.replace("_", " ").lower()
        index = self.link_index()
        # Direct hit on a body-visible display form.
        for form, targets in index.items():
            if form.lower() == normalized:
                return targets[0] if len(targets) == 1 else list(targets)
        # Hit on a disambiguated target listed inline alongside a bare form.
        for targets in index.values():
            for target in targets:
                if target.lower() == normalized:
                    return target
        return None


def _make_summary(content: str, max_chars: int = 500) -> str:
    head = content[:max_chars]
    last_period = head.rfind(".")
    return head[: last_period + 1] if last_period != -1 else head


class WikiClient:
    """Async client for the English Wikipedia MediaWiki API."""

    def __init__(
        self,
        user_agent: str,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ):
        if not user_agent or "example" in user_agent.lower():
            logger.warning(
                "Using a default/example User-Agent; Wikipedia may rate-limit. "
                "Set WIKIGAME_USER_AGENT to identify your tool and contact."
            )
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            timeout=timeout,
            follow_redirects=True,
        )
        self._cache: dict[str, WikiPage] = {}

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> WikiClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, WikiNonJSONResponse)),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def _request(self, params: dict[str, str]) -> dict:
        full_params = {"format": "json", "formatversion": "2", **params}
        resp = await self._client.get(WIKIPEDIA_API_URL, params=full_params)
        resp.raise_for_status()
        try:
            return resp.json()
        except json.JSONDecodeError as e:
            preview = resp.text[:200].replace("\n", " ")
            logger.warning(
                "MediaWiki returned non-JSON (status=%s): %s",
                resp.status_code,
                preview,
            )
            raise WikiNonJSONResponse(
                f"Non-JSON response from MediaWiki (status {resp.status_code}): {preview!r}"
            ) from e

    async def get_page(self, title: str) -> WikiPage:
        """Fetch a page by title, following redirects and OpenSearch suggestions.

        Disambiguation pages are returned as-is — the caller is expected to
        present the options and let a downstream actor pick one.
        """
        key = title.strip().lower()
        if key in self._cache:
            return self._cache[key]
        page = await self._fetch_page(title)
        self._cache[key] = page
        self._cache[page.title.lower()] = page
        return page

    async def _fetch_page(self, title: str) -> WikiPage:
        page_info: dict | None = None
        all_links: list[str] = []
        params: dict[str, str] = {
            "action": "query",
            "prop": "extracts|links|info|pageprops",
            "titles": title,
            "redirects": "1",
            "explaintext": "1",
            "exsectionformat": "plain",
            "inprop": "url",
            "pllimit": "max",
        }
        while True:
            data = await self._request(params)
            pages = data.get("query", {}).get("pages", [])
            if not pages:
                raise WikiPageNotFound(title)
            current = pages[0]
            if current.get("missing"):
                suggestion = await self._suggest(title)
                if suggestion and suggestion.lower() != title.lower():
                    return await self._fetch_page(suggestion)
                raise WikiPageNotFound(title)
            if page_info is None:
                page_info = current
            all_links.extend(link["title"] for link in current.get("links", []))
            cont = data.get("continue")
            if not cont:
                break
            params = {**params, **{k: str(v) for k, v in cont.items()}}

        assert page_info is not None

        # Disambiguation pages are returned as-is. The agent traverses them like
        # any other page (it gets the body, picks an option from <link> tags,
        # and clicks). Auto-resolving here used to follow `all_links[0]`, which
        # is whatever MediaWiki's links API returned first (pageid/alphabetical),
        # not the document order of the options — e.g. on "Lemonade
        # (disambiguation)" it picked "Boys Noize" (linked from a navbox) over
        # any actual disambig option. It also broke fair-play: a human lands on
        # the disambig page and chooses; the agent must do the same.
        content = page_info.get("extract", "")
        return WikiPage(
            title=page_info["title"],
            url=page_info.get("fullurl", ""),
            content=content,
            summary=_make_summary(content),
            links=tuple(all_links),
        )

    async def _suggest(self, query: str) -> str | None:
        """Use OpenSearch to fall back to a near-match title."""
        data = await self._request({"action": "opensearch", "search": query, "limit": "1"})
        # opensearch shape: [query, [titles], [descriptions], [urls]]
        if isinstance(data, list) and len(data) > 1 and data[1]:
            return data[1][0]
        return None
