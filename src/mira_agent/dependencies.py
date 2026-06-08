from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated

from fastapi import Depends, Header

from mira_agent.auth import extract_bearer_token, verify_supabase_token
from mira_agent.config import Settings, get_settings
from mira_agent.exceptions import ApiError
from mira_agent.repositories.rls_client import RlsClient
from mira_agent.schemas.auth import CurrentUser, OrgRole


def settings_dep() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(settings_dep)]
AuthorizationHeader = Annotated[str | None, Header()]


async def require_user(
    settings: SettingsDep,
    authorization: AuthorizationHeader = None,
) -> CurrentUser:
    token = extract_bearer_token(authorization)
    return await verify_supabase_token(token, settings)


def get_rls_client(
    user: Annotated[CurrentUser, Depends(require_user)],
    settings: SettingsDep,
) -> RlsClient:
    return RlsClient(
        postgrest_url=settings.postgrest_url,
        anon_key=settings.supabase_anon_key,
        user_token=user.token,
    )


def get_write_client(
    _user: Annotated[CurrentUser, Depends(require_user)],
    settings: SettingsDep,
) -> RlsClient:
    if not settings.has_supabase_write_config:
        raise ApiError(
            "BACKEND_WRITE_NOT_CONFIGURED",
            "Backend persistence is not configured.",
            500,
        )
    return RlsClient(
        postgrest_url=settings.postgrest_url,
        anon_key=settings.supabase_service_role_key,
        user_token=settings.supabase_service_role_key,
    )


async def require_org_role(
    *,
    client: RlsClient,
    org_id: str,
    user: CurrentUser,
    allowed_roles: Iterable[OrgRole],
) -> OrgRole:
    rows = await client.select(
        "organization_members",
        select="role",
        filters={"org_id": f"eq.{org_id}", "user_id": f"eq.{user.id}"},
        limit=1,
    )
    if not rows:
        raise ApiError("ORG_FORBIDDEN", "You do not have access to this organization.", 403)

    role = rows[0].get("role")
    if role not in set(allowed_roles):
        raise ApiError(
            "APPROVAL_FORBIDDEN",
            "This organization role cannot perform the action.",
            403,
        )
    return role  # type: ignore[return-value]
