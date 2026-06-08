from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

import httpx

from mira_agent.config import get_settings

DEMO_ORG_ID = "11111111-1111-4111-8111-111111111111"
OUTSIDER_ORG_ID = "22222222-2222-4222-8222-222222222222"
ANALYST_EMAIL = "analyst@mira.local"
ADMIN_EMAIL = "admin@mira.local"
OUTSIDER_EMAIL = "outsider@mira.local"
DEMO_PASSWORD_KEY = "DEMO_PASSWORD"
DEMO_ENV_PATH = Path(".demo.env")


def _read_demo_env() -> dict[str, str]:
    if not DEMO_ENV_PATH.exists():
        return {}
    values: dict[str, str] = {}
    for line in DEMO_ENV_PATH.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key:
            values[key] = value.strip().strip("\"'")
    return values


def _load_demo_password() -> str:
    if password := os.getenv(DEMO_PASSWORD_KEY):
        return password
    if password := _read_demo_env().get(DEMO_PASSWORD_KEY):
        return password
    return f"mira_{secrets.token_urlsafe(24)}A1!"


DEMO_PASSWORD = _load_demo_password()


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
            "user_metadata": {"source": "mira_demo_seed"},
        },
        timeout=10.0,
    )
    if response.status_code in {200, 201}:
        return
    if response.status_code == 422:
        _update_user_password(_find_user_id(email))
        return
    response.raise_for_status()


def _find_user_id(email: str) -> str:
    settings = get_settings()
    response = httpx.get(
        f"{settings.auth_url}/admin/users",
        params={"page": 1, "per_page": 1000},
        headers=_service_headers(),
        timeout=10.0,
    )
    response.raise_for_status()
    payload = response.json()
    users = payload.get("users", []) if isinstance(payload, dict) else payload
    if not isinstance(users, list):
        raise RuntimeError("Supabase admin user list response was not recognized.")
    for user in users:
        if not isinstance(user, dict):
            continue
        if str(user.get("email", "")).lower() != email.lower():
            continue
        user_id = user.get("id")
        if isinstance(user_id, str):
            return user_id
    raise RuntimeError(f"Could not find existing demo user {email}.")


def _update_user_password(user_id: str) -> None:
    settings = get_settings()
    response = httpx.put(
        f"{settings.auth_url}/admin/users/{user_id}",
        headers=_service_headers(),
        json={
            "password": DEMO_PASSWORD,
            "email_confirm": True,
            "user_metadata": {"source": "mira_demo_seed"},
        },
        timeout=10.0,
    )
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
    token_lines = [
        f"DEMO_ORG_ID={state.demo_org_id}",
        f"OUTSIDER_ORG_ID={state.outsider_org_id}",
        f"ANALYST_JWT={state.analyst_jwt}",
        f"ADMIN_JWT={state.admin_jwt}",
        f"OUTSIDER_JWT={state.outsider_jwt}",
    ]
    env_lines = [f"{DEMO_PASSWORD_KEY}={DEMO_PASSWORD}", *token_lines]
    with open(".demo.env", "w", encoding="utf-8") as handle:
        handle.write("\n".join(env_lines) + "\n")
    if os.getenv("MIRA_PRINT_DEMO_TOKENS") == "1":
        print("\n".join(token_lines))
    else:
        print("Demo users and orgs are ready. Tokens written to .demo.env.")


if __name__ == "__main__":
    main()
