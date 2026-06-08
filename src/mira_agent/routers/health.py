from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends

from mira_agent.config import Settings
from mira_agent.dependencies import settings_dep

router = APIRouter(tags=["health"])
SettingsDep = Annotated[Settings, Depends(settings_dep)]


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@router.get("/health/db")
async def db_health(settings: SettingsDep) -> dict[str, str]:
    if not settings.has_supabase_runtime_config:
        return {"status": "unhealthy"}

    headers = {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {settings.supabase_anon_key}",
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{settings.postgrest_url}/profiles",
                params={"select": "id", "limit": 1},
                headers=headers,
            )
    except httpx.HTTPError:
        return {"status": "unhealthy"}

    if response.status_code >= 400:
        return {"status": "unhealthy"}
    return {"status": "healthy"}
