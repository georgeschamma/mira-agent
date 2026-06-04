from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from mira_agent.config import Settings
from mira_agent.dependencies import settings_dep
from mira_agent.schemas.report import RuntimeConfigResponse

router = APIRouter(prefix="/api", tags=["config"])
SettingsDep = Annotated[Settings, Depends(settings_dep)]


@router.get("/config", response_model=RuntimeConfigResponse)
async def runtime_config(settings: SettingsDep) -> RuntimeConfigResponse:
    return RuntimeConfigResponse(
        app_name="MIRA Agent",
        app_version="0.1.0",
        supabase_url=settings.supabase_url,
        supabase_anon_key=settings.supabase_anon_key,
    )
