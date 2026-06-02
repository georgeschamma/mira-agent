import os

import pytest
from fastapi.testclient import TestClient

from mira_agent.config import get_settings
from mira_agent.main import app
from scripts.create_demo_users import DEMO_ORG_ID, ensure_demo_state

pytestmark = pytest.mark.integration


def _require_rls_tests_enabled() -> None:
    if os.getenv("RUN_RLS_TESTS") != "1":
        pytest.skip("Set RUN_RLS_TESTS=1 to run real Supabase JWT/RLS tests.")


def _require_phase_1_integrations_configured() -> None:
    settings = get_settings()
    if not settings.has_llm_config or not settings.has_exa_config:
        pytest.skip("Set LLM and Exa env keys to run the Phase 1 real analysis flow.")


def test_real_jwt_org_rbac_and_rls_flow() -> None:
    _require_rls_tests_enabled()
    _require_phase_1_integrations_configured()
    state = ensure_demo_state()
    client = TestClient(app)
    payload = {
        "org_id": DEMO_ORG_ID,
        "product": "MIRA",
        "audience": "B2B marketers",
        "channels": ["linkedin"],
        "budget": 1000,
        "goal": "book demos",
    }

    analyze_response = client.post(
        "/api/analyze",
        headers={"Authorization": f"Bearer {state.analyst_jwt}"},
        json=payload,
    )
    assert analyze_response.status_code == 200, analyze_response.text
    body = analyze_response.json()
    assert body["recommendations"]
    assert all(item["source"] for item in body["recommendations"])
    legacy_stub_source = "phase_0_5" + "_spine_stub"
    assert all(item["source"] != legacy_stub_source for item in body["recommendations"])
    approval_recommendation = next(
        item for item in body["recommendations"] if item["needs_approval"]
    )
    assert body["approval_id"]

    analyst_approval_response = client.post(
        f"/api/action-sheets/{body['action_sheet_id']}/approvals/{approval_recommendation['id']}",
        headers={"Authorization": f"Bearer {state.analyst_jwt}"},
        json={"status": "approved"},
    )
    assert analyst_approval_response.status_code == 403
    assert analyst_approval_response.json()["error"]["code"] == "APPROVAL_FORBIDDEN"

    admin_approval_response = client.post(
        f"/api/action-sheets/{body['action_sheet_id']}/approvals/{approval_recommendation['id']}",
        headers={"Authorization": f"Bearer {state.admin_jwt}"},
        json={"status": "approved"},
    )
    assert admin_approval_response.status_code == 200, admin_approval_response.text
    assert admin_approval_response.json()["status"] == "approved"

    outsider_response = client.post(
        "/api/analyze",
        headers={"Authorization": f"Bearer {state.outsider_jwt}"},
        json=payload,
    )
    assert outsider_response.status_code == 403
    assert outsider_response.json()["error"]["code"] == "ORG_FORBIDDEN"
