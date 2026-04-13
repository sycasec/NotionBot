import logging
from html.parser import HTMLParser

import requests
from langchain_core.tools import tool

log = logging.getLogger(__name__)

_DDG_URL = "https://html.duckduckgo.com/html/"


class _DDGParser(HTMLParser):
    """Parse DuckDuckGo HTML results into a list of dicts."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._current: dict[str, str] = {}
        self._in_title = False
        self._in_snippet = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        cls = attr_dict.get("class") or ""
        if tag == "a" and "result__a" in cls:
            self._in_title = True
            self._current["url"] = attr_dict.get("href", "")
        elif tag == "a" and "result__snippet" in cls:
            self._in_snippet = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_title:
            self._in_title = False
        elif tag == "a" and self._in_snippet:
            self._in_snippet = False
            if self._current:
                self.results.append(dict(self._current))
                self._current.clear()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._current["title"] = self._current.get("title", "") + data
        elif self._in_snippet:
            self._current["snippet"] = self._current.get("snippet", "") + data


def _format_results(query: str, results: list[dict[str, str]]) -> str:
    if not results:
        return f"No results found for '{query}'."
    lines = []
    for r in results[:5]:
        title = r.get("title", "No title")
        snippet = r.get("snippet", "")
        lines.append(f"- **{title}**\n  {snippet}")
    return f"Search results for '{query}':\n\n" + "\n\n".join(lines)


@tool
def web_search(query: str) -> str:
    """Search the web using DuckDuckGo and return the top results.
    query: search query, e.g. 'latest Python news'
    Returns a summary of the top search results.
    """
    try:
        resp = requests.post(
            _DDG_URL,
            data={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"},
            timeout=10,
        )
        resp.raise_for_status()

        parser = _DDGParser()
        parser.feed(resp.text)
        return _format_results(query, parser.results)
    except requests.exceptions.RequestException as e:
        log.warning("Web search error for '%s': %s", query, e)
        return f"Error searching for '{query}': {e}"
