from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(slots=True)
class PostgrestError(Exception):
    status_code: int
    message: str


class RlsClient:
    def __init__(
        self,
        *,
        postgrest_url: str,
        anon_key: str,
        user_token: str,
        timeout: float = 10.0,
    ) -> None:
        self.postgrest_url = postgrest_url.rstrip("/")
        self.anon_key = anon_key
        self.user_token = user_token
        self.timeout = timeout

    @property
    def headers(self) -> dict[str, str]:
        return {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {self.user_token}",
            "Content-Type": "application/json",
        }

    async def select(
        self,
        table: str,
        *,
        select: str = "*",
        filters: Mapping[str, str] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {"select": select}
        if filters:
            params.update(filters)
        if limit is not None:
            params["limit"] = limit
        return await self._request("GET", table, params=params)

    async def insert(self, table: str, payload: Mapping[str, Any]) -> list[dict[str, Any]]:
        return await self._request(
            "POST",
            table,
            json=payload,
            headers={"Prefer": "return=representation"},
        )

    async def upsert(
        self,
        table: str,
        payload: Mapping[str, Any] | list[Mapping[str, Any]],
        *,
        on_conflict: str,
    ) -> list[dict[str, Any]]:
        return await self._request(
            "POST",
            table,
            params={"on_conflict": on_conflict},
            json=payload,
            headers={"Prefer": "resolution=merge-duplicates,return=representation"},
        )

    async def update(
        self,
        table: str,
        payload: Mapping[str, Any],
        *,
        filters: Mapping[str, str],
    ) -> list[dict[str, Any]]:
        return await self._request(
            "PATCH",
            table,
            params=dict(filters),
            json=payload,
            headers={"Prefer": "return=representation"},
        )

    async def _request(
        self,
        method: str,
        table: str,
        *,
        params: Mapping[str, str | int] | None = None,
        json: Any | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        request_headers = self.headers | dict(headers or {})
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(
                method,
                f"{self.postgrest_url}/{table}",
                params=params,
                json=json,
                headers=request_headers,
            )
        if response.status_code >= 400:
            raise PostgrestError(response.status_code, response.text)
        if not response.content:
            return []
        data = response.json()
        if isinstance(data, list):
            return data
        return [data]

