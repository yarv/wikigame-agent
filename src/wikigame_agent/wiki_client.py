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
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import unquote

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


# Wikipedia namespace prefixes that are NOT article-namespace (ns=0). Anchors
# whose target starts with one of these (case-insensitive) followed by ':' are
# meta/chrome links the human game player cannot follow as a move.
_NON_ARTICLE_NAMESPACES = frozenset(
    p.lower()
    for p in (
        "File",
        "Image",
        "Media",
        "Special",
        "Category",
        "Template",
        "Help",
        "Wikipedia",
        "Project",
        "Portal",
        "Book",
        "Draft",
        "User",
        "MediaWiki",
        "Module",
        "TimedText",
        "Talk",
        "User talk",
        "Wikipedia talk",
        "File talk",
        "Image talk",
        "Template talk",
        "Help talk",
        "Category talk",
        "Portal talk",
        "Book talk",
        "Draft talk",
        "MediaWiki talk",
        "Module talk",
        "TimedText talk",
    )
)

# CSS class names whose subtrees are chrome — links inside them are visible
# to a human reader but conceptually outside the article body proper, so we
# don't admit them as game moves. We also prefix-match these (e.g.
# `infobox-vcard`).
_CHROME_CLASSES = frozenset(
    (
        "infobox",
        "navbox",
        "sidebar",
        "hatnote",
        "reference",
        "references",
        "mw-references-wrap",
        "thumbcaption",
        "gallery",
        "metadata",
        "mbox-text",
        "ambox",
        "mw-editsection",
        "noprint",
        "shortdescription",
    )
)


def _has_chrome_class(attrs: list[tuple[str, str | None]]) -> bool:
    for name, value in attrs:
        if name == "class" and value:
            classes = value.split()
            for c in classes:
                if c in _CHROME_CLASSES:
                    return True
                for prefix in _CHROME_CLASSES:
                    if c.startswith(prefix + "-"):
                        return True
        elif name == "role" and value == "navigation":
            return True
    return False


def _parse_wiki_href(href: str | None) -> str | None:
    """Return the target page title for an internal article link, else None.

    Accepts only `/wiki/<Title>` hrefs in the article namespace. Strips
    fragments and query strings, decodes percent-escapes, and normalizes
    underscores to spaces. Rejects external URLs, fragment-only links,
    and non-article namespaces.
    """
    if not href or not href.startswith("/wiki/"):
        return None
    path = href[len("/wiki/") :]
    path = path.split("#", 1)[0].split("?", 1)[0]
    if not path:
        return None
    try:
        title = unquote(path).replace("_", " ")
    except UnicodeDecodeError:
        return None
    colon_idx = title.find(":")
    if colon_idx > 0:
        prefix = title[:colon_idx].lower()
        if prefix in _NON_ARTICLE_NAMESPACES:
            return None
    return title


class _BodyLinkExtractor(HTMLParser):
    """Collect anchor `(display_label, target_title)` pairs from article HTML.

    Skips anchors whose `href` is not a local `/wiki/X` article link, and
    anchors that appear nested anywhere inside an element whose class list
    matches `_CHROME_CLASSES`. The display label is the anchor's rendered
    text content, with whitespace collapsed.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[tuple[str, str]] = []
        self._chrome_depth = 0
        self._tag_stack: list[tuple[str, bool]] = []
        self._anchor_target: str | None = None
        self._anchor_text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        is_chrome = _has_chrome_class(attrs)
        if is_chrome:
            self._chrome_depth += 1
        self._tag_stack.append((tag, is_chrome))
        if tag == "a" and self._chrome_depth == 0 and self._anchor_target is None:
            href = next((v for n, v in attrs if n == "href"), None)
            target = _parse_wiki_href(href)
            if target is not None:
                self._anchor_target = target
                self._anchor_text_parts = []

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self._tag_stack) - 1, -1, -1):
            if self._tag_stack[i][0] == tag:
                _, was_chrome = self._tag_stack.pop(i)
                if was_chrome:
                    self._chrome_depth -= 1
                break
        if tag == "a" and self._anchor_target is not None:
            label = " ".join("".join(self._anchor_text_parts).split())
            if label:
                self.anchors.append((label, self._anchor_target))
            self._anchor_target = None
            self._anchor_text_parts = []

    def handle_data(self, data: str) -> None:
        if self._anchor_target is not None and self._chrome_depth == 0:
            self._anchor_text_parts.append(data)


def _build_link_index_from_html(body_html: str, self_title: str) -> dict[str, list[str]]:
    """Display form -> list of target page titles, derived from body anchors.

    Self-links and duplicate targets within a bucket are filtered.
    """
    parser = _BodyLinkExtractor()
    parser.feed(body_html)
    parser.close()
    index: dict[str, list[str]] = {}
    self_lower = self_title.lower()
    for label, target in parser.anchors:
        if target.lower() == self_lower:
            continue
        bucket = index.setdefault(label, [])
        if target not in bucket:
            bucket.append(target)
    return index


@dataclass(frozen=True)
class WikiPage:
    title: str
    url: str
    content: str
    summary: str
    links: tuple[str, ...]
    body_html: str = ""
    _link_index: dict[str, list[str]] = field(default_factory=dict)

    def link_index(self) -> dict[str, list[str]]:
        """Display form -> list of target page titles, for body-visible links.

        The set of admissible moves is the set of `<a href="/wiki/X">label</a>`
        anchors in the article body HTML, excluding anchors nested inside
        chrome (infobox, navbox, sidebar, hatnote, references, image
        captions, etc.) and non-article namespaces (File:, Category:,
        Template:, ...). The bucket value is the list of disambiguated
        targets a bare display form can resolve to (Wikipedia editors use
        the pipe-trick to render "Mary Poppins" while linking to
        "Mary Poppins (film)"); the caller surfaces the ambiguity.
        """
        return self._link_index

    def permitted_links(self) -> list[str]:
        """Display forms agents can click. See :meth:`link_index`."""
        return list(self._link_index.keys())

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
        for form, targets in self._link_index.items():
            if form.lower() == normalized:
                return targets[0] if len(targets) == 1 else list(targets)
        for targets in self._link_index.values():
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
        """Fetch a page by title, resolving redirects and disambiguation."""
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

        if "disambiguation" in page_info.get("pageprops", {}):
            if not all_links:
                raise WikiPageNotFound(f"Disambiguation page with no options: {title}")
            logger.info("Resolving disambiguation %r -> %r", title, all_links[0])
            return await self._fetch_page(all_links[0])

        canonical_title = page_info["title"]
        body_html = await self._fetch_body_html(canonical_title)
        content = page_info.get("extract", "")
        return WikiPage(
            title=canonical_title,
            url=page_info.get("fullurl", ""),
            content=content,
            summary=_make_summary(content),
            links=tuple(all_links),
            body_html=body_html,
            _link_index=_build_link_index_from_html(body_html, canonical_title),
        )

    async def _fetch_body_html(self, title: str) -> str:
        """Fetch the rendered article body HTML via action=parse.

        This is the same HTML Wikipedia would serve to a human reader. The
        link-set the agent is allowed to click is derived from anchors in
        this HTML, not from `prop=links` (which over-permits links visible
        only in infoboxes, navboxes, references and other chrome).
        """
        data = await self._request(
            {
                "action": "parse",
                "page": title,
                "prop": "text",
                "redirects": "1",
                "disableeditsection": "1",
                "disabletoc": "1",
            }
        )
        parse = data.get("parse")
        if not parse:
            return ""
        text = parse.get("text", "")
        if isinstance(text, dict):
            text = text.get("*", "")
        return text or ""

    async def _suggest(self, query: str) -> str | None:
        """Use OpenSearch to fall back to a near-match title."""
        data = await self._request({"action": "opensearch", "search": query, "limit": "1"})
        # opensearch shape: [query, [titles], [descriptions], [urls]]
        if isinstance(data, list) and len(data) > 1 and data[1]:
            return data[1][0]
        return None
