from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from mira_agent.config import get_settings

DEMO_ORG_ID = "11111111-1111-4111-8111-111111111111"
OUTSIDER_ORG_ID = "22222222-2222-4222-8222-222222222222"
ANALYST_EMAIL = "analyst@mira.local"
ADMIN_EMAIL = "admin@mira.local"
OUTSIDER_EMAIL = "outsider@mira.local"
DEMO_PASSWORD = "MiraPhase05!"


@dataclass(slots=True)
class DemoState:
    demo_org_id: str
    outsider_org_id: str
    analyst_jwt: str
    admin_jwt: str
    outsider_jwt: str
    analyst_user_id: str
    admin_user_id: str
    outsider_user_id: str


def _service_headers() -> dict[str, str]:
    settings = get_settings()
    if not settings.supabase_service_role_key or settings.supabase_service_role_key.startswith(
        "replace-with"
    ):
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is required for demo user setup.")
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
    }


def _anon_headers() -> dict[str, str]:
    settings = get_settings()
    if not settings.supabase_anon_key or settings.supabase_anon_key.startswith("replace-with"):
        raise RuntimeError("SUPABASE_ANON_KEY is required for demo user setup.")
    return {
        "apikey": settings.supabase_anon_key,
        "Content-Type": "application/json",
    }


def _create_user(email: str) -> None:
    settings = get_settings()
    response = httpx.post(
        f"{settings.auth_url}/admin/users",
        headers=_service_headers(),
        json={
            "email": email,
            "password": DEMO_PASSWORD,
            "email_confirm": True,
            "user_metadata": {"source": "mira_phase_0_5"},
        },
        timeout=10.0,
    )
    if response.status_code not in {200, 201, 422}:
        response.raise_for_status()


def _sign_in(email: str) -> tuple[str, str]:
    settings = get_settings()
    response = httpx.post(
        f"{settings.auth_url}/token",
        params={"grant_type": "password"},
        headers=_anon_headers(),
        json={"email": email, "password": DEMO_PASSWORD},
        timeout=10.0,
    )
    response.raise_for_status()
    payload = response.json()
    return payload["access_token"], payload["user"]["id"]


def _service_upsert(table: str, payload: list[dict[str, object]], on_conflict: str) -> None:
    settings = get_settings()
    response = httpx.post(
        f"{settings.postgrest_url}/{table}",
        params={"on_conflict": on_conflict},
        headers=_service_headers()
        | {"Prefer": "resolution=merge-duplicates,return=minimal"},
        json=payload,
        timeout=10.0,
    )
    response.raise_for_status()


def ensure_demo_state() -> DemoState:
    for email in (ANALYST_EMAIL, ADMIN_EMAIL, OUTSIDER_EMAIL):
        _create_user(email)

    analyst_jwt, analyst_id = _sign_in(ANALYST_EMAIL)
    admin_jwt, admin_id = _sign_in(ADMIN_EMAIL)
    outsider_jwt, outsider_id = _sign_in(OUTSIDER_EMAIL)

    _service_upsert(
        "organizations",
        [
            {"id": DEMO_ORG_ID, "name": "MIRA Demo Org", "created_by": admin_id},
            {"id": OUTSIDER_ORG_ID, "name": "MIRA Outsider Org", "created_by": outsider_id},
        ],
        "id",
    )
    _service_upsert(
        "organization_members",
        [
            {"org_id": DEMO_ORG_ID, "user_id": analyst_id, "role": "analyst"},
            {"org_id": DEMO_ORG_ID, "user_id": admin_id, "role": "admin"},
            {"org_id": OUTSIDER_ORG_ID, "user_id": outsider_id, "role": "admin"},
        ],
        "org_id,user_id",
    )

    return DemoState(
        demo_org_id=DEMO_ORG_ID,
        outsider_org_id=OUTSIDER_ORG_ID,
        analyst_jwt=analyst_jwt,
        admin_jwt=admin_jwt,
        outsider_jwt=outsider_jwt,
        analyst_user_id=analyst_id,
        admin_user_id=admin_id,
        outsider_user_id=outsider_id,
    )


def main() -> None:
    state = ensure_demo_state()
    env_lines = [
        f"DEMO_ORG_ID={state.demo_org_id}",
        f"OUTSIDER_ORG_ID={state.outsider_org_id}",
        f"ANALYST_JWT={state.analyst_jwt}",
        f"ADMIN_JWT={state.admin_jwt}",
        f"OUTSIDER_JWT={state.outsider_jwt}",
    ]
    with open(".demo.env", "w", encoding="utf-8") as handle:
        handle.write("\n".join(env_lines) + "\n")
    if os.getenv("MIRA_PRINT_DEMO_TOKENS") == "1":
        print("\n".join(env_lines))
    else:
        print("Demo users and orgs are ready. Tokens written to .demo.env.")


if __name__ == "__main__":
    main()
