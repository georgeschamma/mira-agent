from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from exa_py import AsyncExa

from mira_agent.graph.state import ResearchFinding


class ResearchClient(Protocol):
    async def search(self, query: str, *, num_results: int) -> list[ResearchFinding]:
        ...


class ExaResearchClient:
    def __init__(self, *, api_key: str) -> None:
        self._client = AsyncExa(api_key=api_key)

    async def search(self, query: str, *, num_results: int) -> list[ResearchFinding]:
        response = await self._client.search(
            query,
            num_results=num_results,
            contents={"highlights": True},
        )
        return normalize_search_response(response)


def normalize_search_response(response: Any) -> list[ResearchFinding]:
    findings: list[ResearchFinding] = []
    for item in _get_value(response, "results", []):
        url = _get_value(item, "url") or _get_value(item, "id")
        title = _get_value(item, "title") or url
        if not url or not title:
            continue

        findings.append(
            ResearchFinding(
                title=str(title),
                url=str(url),
                highlights=_normalize_highlights(_get_value(item, "highlights", [])),
                published_date=_get_optional_str(item, "publishedDate")
                or _get_optional_str(item, "published_date"),
            )
        )
    return findings


def _get_value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _get_optional_str(item: Any, key: str) -> str | None:
    value = _get_value(item, key)
    if value is None:
        return None
    return str(value)


def _normalize_highlights(raw_highlights: Any) -> list[str]:
    if not raw_highlights:
        return []
    if isinstance(raw_highlights, str):
        return [raw_highlights]
    if not isinstance(raw_highlights, Sequence):
        return []

    highlights: list[str] = []
    for item in raw_highlights:
        if isinstance(item, str):
            highlights.append(item)
            continue
        text = _get_value(item, "text") or _get_value(item, "highlight")
        if text:
            highlights.append(str(text))
    return highlights
