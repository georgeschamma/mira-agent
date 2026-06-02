from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import Header

from mira_agent.config import Settings
from mira_agent.exceptions import ApiError
from mira_agent.schemas.auth import CurrentUser


def extract_bearer_token(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization:
        raise ApiError("AUTH_REQUIRED", "Missing Authorization bearer token.", 401)
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ApiError("AUTH_INVALID", "Authorization header must use Bearer token.", 401)
    return token.strip()


async def verify_supabase_token(token: str, settings: Settings) -> CurrentUser:
    if not settings.has_supabase_runtime_config:
        raise ApiError("AUTH_INVALID", "Supabase runtime auth is not configured.", 401)

    headers = {
        "apikey": settings.supabase_anon_key,
        "Authorization": f"Bearer {token}",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{settings.auth_url}/user", headers=headers)
    except httpx.HTTPError as exc:
        raise ApiError("AUTH_INVALID", "Could not verify Supabase JWT.", 401) from exc

    if response.status_code != 200:
        raise ApiError("AUTH_INVALID", "Invalid or expired Supabase JWT.", 401)

    payload = response.json()
    user_id = payload.get("id")
    if not user_id:
        raise ApiError("AUTH_INVALID", "Supabase JWT did not resolve to a user.", 401)

    return CurrentUser(id=user_id, email=payload.get("email"), token=token)

