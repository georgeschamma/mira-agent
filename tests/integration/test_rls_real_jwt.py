import os
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from mira_agent.config import get_settings
from mira_agent.main import app
from scripts.create_demo_users import DEMO_ORG_ID, ensure_demo_state

pytestmark = pytest.mark.integration


def _require_rls_tests_enabled() -> None:
    if os.getenv("RUN_RLS_TESTS") != "1":
        pytest.skip("Set RUN_RLS_TESTS=1 to run real Supabase JWT/RLS tests.")
    settings = get_settings()
    hostname = urlparse(settings.supabase_url).hostname
    if hostname not in {"127.0.0.1", "localhost"} and os.getenv("RUN_REMOTE_RLS_TESTS") != "1":
        pytest.skip(
            "Refusing to mutate non-local Supabase. Set RUN_REMOTE_RLS_TESTS=1 to opt in."
        )


def _require_phase_1_integrations_configured() -> None:
    settings = get_settings()
    if not settings.has_llm_config or not settings.has_exa_config:
        pytest.skip("Set LLM and Exa env keys to run the real analysis flow.")


def _headers(token: str, api_key: str) -> dict[str, str]:
    return {
        "apikey": api_key,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _delete_campaign(
    client: httpx.Client,
    *,
    postgrest_url: str,
    service_headers: dict[str, str],
    campaign_id: str,
) -> None:
    client.delete(
        f"{postgrest_url}/campaigns",
        headers=service_headers,
        params={"id": f"eq.{campaign_id}"},
    )


def test_real_jwt_denies_direct_generated_writes_and_public_helper_rpcs() -> None:
    _require_rls_tests_enabled()
    settings = get_settings()
    state = ensure_demo_state()
    campaign_id = str(uuid4())
    run_id = str(uuid4())
    action_sheet_id = str(uuid4())
    approval_id = str(uuid4())
    analyst_headers = _headers(state.analyst_jwt, settings.supabase_anon_key)
    outsider_headers = _headers(state.outsider_jwt, settings.supabase_anon_key)
    service_headers = _headers(
        settings.supabase_service_role_key,
        settings.supabase_service_role_key,
    )

    with httpx.Client(timeout=10.0) as client:
        direct_campaign_id: str | None = None
        try:
            service_campaign = client.post(
                f"{settings.postgrest_url}/campaigns",
                headers=service_headers,
                json={
                    "id": campaign_id,
                    "org_id": state.demo_org_id,
                    "created_by": state.analyst_user_id,
                    "brief": {
                        "org_id": state.demo_org_id,
                        "product": "RLS test",
                        "audience": "RLS test",
                        "channels": ["test"],
                        "budget": 1,
                        "goal": "RLS test",
                    },
                },
            )
            assert service_campaign.status_code == 201, service_campaign.text
            service_run = client.post(
                f"{settings.postgrest_url}/campaign_runs",
                headers=service_headers,
                json={"id": run_id, "campaign_id": campaign_id, "status": "running"},
            )
            assert service_run.status_code == 201, service_run.text
            service_sheet = client.post(
                f"{settings.postgrest_url}/action_sheets",
                headers=service_headers,
                json={
                    "id": action_sheet_id,
                    "campaign_id": campaign_id,
                    "run_id": run_id,
                    "recommendations": [],
                    "model_used": "test",
                    "document_markdown": "# Test",
                    "document_status": "pending",
                },
            )
            assert service_sheet.status_code == 201, service_sheet.text
            service_approval = client.post(
                f"{settings.postgrest_url}/action_sheet_approvals",
                headers=service_headers,
                json={
                    "id": approval_id,
                    "action_sheet_id": action_sheet_id,
                    "recommendation_id": "document",
                    "status": "pending",
                },
            )
            assert service_approval.status_code == 201, service_approval.text

            direct_campaign = client.post(
                f"{settings.postgrest_url}/campaigns",
                headers=analyst_headers,
                json={
                    "org_id": state.demo_org_id,
                    "created_by": state.analyst_user_id,
                    "brief": {"product": "forged"},
                },
            )
            if direct_campaign.status_code == 201:
                direct_campaign_id = direct_campaign.json()[0]["id"]
            direct_audit = client.post(
                f"{settings.postgrest_url}/audit_log",
                headers=analyst_headers,
                json={
                    "campaign_id": campaign_id,
                    "run_id": run_id,
                    "step_index": 99,
                    "node": "forged-client",
                    "summary": "Forged directly with a browser-equivalent JWT.",
                    "source": "brief:forged",
                    "confidence": "high",
                    "model_used": "forged-model",
                },
            )
            outsider_rpc = client.post(
                f"{settings.postgrest_url}/rpc/campaign_org",
                headers=outsider_headers,
                json={"target_campaign": campaign_id},
            )

            api_client = TestClient(app)
            admin_approval = api_client.post(
                f"/api/action-sheets/{action_sheet_id}/approvals/document",
                headers={"Authorization": f"Bearer {state.admin_jwt}"},
                json={"status": "approved"},
            )
            admin_report = api_client.get(
                f"/api/action-sheets/{action_sheet_id}",
                headers={"Authorization": f"Bearer {state.admin_jwt}"},
            )
        finally:
            _delete_campaign(
                client,
                postgrest_url=settings.postgrest_url,
                service_headers=service_headers,
                campaign_id=campaign_id,
            )
            if direct_campaign_id:
                _delete_campaign(
                    client,
                    postgrest_url=settings.postgrest_url,
                    service_headers=service_headers,
                    campaign_id=direct_campaign_id,
                )

    assert direct_campaign.status_code >= 400
    assert direct_audit.status_code >= 400
    assert outsider_rpc.status_code >= 400
    assert admin_approval.status_code == 200, admin_approval.text
    assert admin_report.status_code == 200, admin_report.text
    assert admin_report.json()["document_status"] == "approved"
    assert admin_report.json()["approvals"][0]["status"] == "approved"


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

    report_response = client.get(
        f"/api/action-sheets/{body['action_sheet_id']}",
        headers={"Authorization": f"Bearer {state.analyst_jwt}"},
    )
    assert report_response.status_code == 200, report_response.text
    report_body = report_response.json()
    assert report_body["action_sheet_id"] == body["action_sheet_id"]
    assert report_body["recommendations"]
    assert all(item["source"] for item in report_body["recommendations"])

    audit_response = client.get(
        f"/api/runs/{body['run_id']}/audit",
        headers={"Authorization": f"Bearer {state.analyst_jwt}"},
    )
    assert audit_response.status_code == 200, audit_response.text
    audit_body = audit_response.json()
    assert [row["node"] for row in audit_body["rows"]] == ["router", "research", "content"]

    outsider_report_response = client.get(
        f"/api/action-sheets/{body['action_sheet_id']}",
        headers={"Authorization": f"Bearer {state.outsider_jwt}"},
    )
    assert outsider_report_response.status_code == 404
    assert outsider_report_response.json()["error"]["code"] == "ACTION_SHEET_NOT_FOUND"

    outsider_audit_response = client.get(
        f"/api/runs/{body['run_id']}/audit",
        headers={"Authorization": f"Bearer {state.outsider_jwt}"},
    )
    assert outsider_audit_response.status_code == 404
    assert outsider_audit_response.json()["error"]["code"] == "AUDIT_TRACE_NOT_FOUND"

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


def test_real_jwt_phase_3_media_plan_and_document_approval_flow() -> None:
    _require_rls_tests_enabled()
    _require_phase_1_integrations_configured()
    state = ensure_demo_state()
    client = TestClient(app)
    files = {
        "crm_csv": (
            "crm.csv",
            "email,company,lifecycle_stage\na@example.com,Acme,lead\n",
            "text/csv",
        ),
        "ga4_csv": (
            "ga4.csv",
            "date,source,medium,channel,cost,conversions,total_revenue\n"
            "2026-05-01,google,cpc,Paid Search,100,4,400\n",
            "text/csv",
        ),
    }
    data = {
        "org_id": DEMO_ORG_ID,
        "brief": "Product: MIRA\nAudience: B2B marketers\nBudget: 1000\nGoal: book demos",
    }

    media_plan_response = client.post(
        "/api/media-plan",
        headers={"Authorization": f"Bearer {state.analyst_jwt}"},
        data=data,
        files=files,
    )
    assert media_plan_response.status_code == 200, media_plan_response.text
    body = media_plan_response.json()

    admin_approval_response = client.post(
        f"/api/action-sheets/{body['action_sheet_id']}/approvals/document",
        headers={"Authorization": f"Bearer {state.admin_jwt}"},
        json={"status": "approved"},
    )
    assert admin_approval_response.status_code == 200, admin_approval_response.text

    report_response = client.get(
        f"/api/action-sheets/{body['action_sheet_id']}",
        headers={"Authorization": f"Bearer {state.admin_jwt}"},
    )
    assert report_response.status_code == 200, report_response.text
    report = report_response.json()
    assert report["document_status"] == "approved"
    assert report["approvals"][0]["status"] == "approved"
