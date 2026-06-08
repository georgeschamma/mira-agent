from typing import Any

import pytest
from pydantic_ai.models.test import TestModel

from mira_agent.config import Settings
from mira_agent.exceptions import ApiError
from mira_agent.graph.graph import run_media_plan_analysis, run_mira_analysis
from mira_agent.graph.state import ResearchFinding
from mira_agent.schemas.analyze import AnalyzeRequest
from mira_agent.schemas.auth import CurrentUser
from mira_agent.schemas.media_plan import MediaPlanGraphRequest


class FakeRlsClient:
    def __init__(self) -> None:
        self.inserts: list[tuple[str, dict[str, Any]]] = []
        self.updates: list[tuple[str, dict[str, Any], dict[str, str]]] = []

    async def insert(self, table: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        self.inserts.append((table, payload))
        return [payload]

    async def update(
        self,
        table: str,
        payload: dict[str, Any],
        *,
        filters: dict[str, str],
    ) -> list[dict[str, Any]]:
        self.updates.append((table, payload, filters))
        return [payload | filters]


class FakeResearchClient:
    async def search(self, query: str, *, num_results: int) -> list[ResearchFinding]:
        assert "MIRA" in query
        assert num_results == 2
        return [
            ResearchFinding(
                title="LinkedIn B2B benchmark",
                url="https://example.com/linkedin-benchmark",
                highlights=["LinkedIn can work well for B2B demo generation."],
            )
        ]


@pytest.mark.asyncio
async def test_run_mira_analysis_writes_audit_sheet_and_approval_rows() -> None:
    client = FakeRlsClient()
    model = TestModel(
        custom_output_args={
            "recommendations": [
                {
                    "id": "rec_linkedin",
                    "domain": "content",
                    "finding": "Use LinkedIn proof content for demo generation.",
                    "source": "https://example.com/linkedin-benchmark",
                    "effort": "low",
                    "impact": "high",
                    "action": "Publish a sourced proof post.",
                    "needs_approval": False,
                },
                {
                    "id": "rec_cta",
                    "domain": "research",
                    "finding": "Tie the campaign CTA to demo bookings.",
                    "source": "brief:goal",
                    "effort": "low",
                    "impact": "medium",
                    "action": "Use booking language in the CTA.",
                    "needs_approval": True,
                },
            ]
        }
    )

    response = await run_mira_analysis(
        client=client,  # type: ignore[arg-type]
        request=AnalyzeRequest(
            org_id="11111111-1111-4111-8111-111111111111",
            product="MIRA",
            audience="B2B marketers",
            channels=["linkedin"],
            budget=1000,
            goal="book demos",
        ),
        user=CurrentUser(id="user_1", token="jwt"),
        settings=Settings(
            llm_model="test-model",
            llm_api_key="test",
            exa_api_key="test",
            exa_num_results=2,
        ),
        research_client=FakeResearchClient(),
        model=model,
    )

    inserted_tables = [table for table, _payload in client.inserts]
    audit_nodes = [
        payload["node"] for table, payload in client.inserts if table == "audit_log"
    ]
    approval_rows = [
        payload for table, payload in client.inserts if table == "action_sheet_approvals"
    ]
    run_statuses = [
        payload["status"] for table, payload, _filters in client.updates if table == "campaign_runs"
    ]

    assert response.approval_id
    legacy_stub_source = "phase_0_5" + "_spine_stub"
    assert response.recommendations[0].source != legacy_stub_source
    assert response.recommendations[0].needs_approval is True
    assert response.recommendations[1].needs_approval is False
    assert "campaigns" in inserted_tables
    assert "action_sheets" in inserted_tables
    assert audit_nodes == ["router", "research", "content"]
    assert len(approval_rows) == 1
    assert approval_rows[0]["recommendation_id"] == "rec_linkedin"
    assert run_statuses[-1] == "done"


@pytest.mark.asyncio
async def test_run_mira_analysis_requires_integration_config_without_fakes() -> None:
    with pytest.raises(ApiError) as exc_info:
        await run_mira_analysis(
            client=FakeRlsClient(),  # type: ignore[arg-type]
            request=AnalyzeRequest(
                org_id="11111111-1111-4111-8111-111111111111",
                product="MIRA",
                audience="B2B marketers",
                channels=["linkedin"],
                budget=1000,
                goal="book demos",
            ),
            user=CurrentUser(id="user_1", token="jwt"),
            settings=Settings(llm_model="test-model", llm_api_key="test", exa_api_key=""),
        )

    assert exc_info.value.code == "INTEGRATION_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_run_media_plan_analysis_writes_phase_3_audit_and_document() -> None:
    client = FakeRlsClient()
    model = TestModel(
        custom_output_args={
            "executive_summary": "Use fixed allocation math.",
            "audience_strategy": "Target leads.",
            "channel_rationale": "Review sparse channel history.",
            "sequencing": "Launch after approval.",
            "risks": "Sparse data is flagged.",
            "claims": [
                {"claim": "Allocation is deterministic.", "source": "performance:allocation"}
            ],
        }
    )

    response = await run_media_plan_analysis(
        client=client,  # type: ignore[arg-type]
        request=MediaPlanGraphRequest(
            org_id="11111111-1111-4111-8111-111111111111",
            brief="Product: MIRA\nAudience: B2B marketers\nBudget: 300\nGoal: book demos",
            crm_csv_text="email,company,lifecycle_stage\na@example.com,Acme,lead\n",
            crm_filename="crm.csv",
            ga4_csv_text="\n".join(
                [
                    "date,source,medium,channel,cost,conversions,total_revenue",
                    "2026-05-01,linkedin,paid,Paid Social,100,4,400",
                    "2026-05-02,linkedin,paid,Paid Social,100,5,500",
                    "2026-05-03,linkedin,paid,Paid Social,100,6,600",
                ]
            ),
            ga4_filename="ga4.csv",
        ),
        user=CurrentUser(id="user_1", token="jwt"),
        settings=Settings(
            llm_model="test-model",
            llm_api_key="test",
            exa_api_key="test",
            exa_num_results=2,
        ),
        research_client=FakeResearchClient(),
        model=model,
    )

    audit_rows = [
        payload for table, payload in client.inserts if table == "audit_log"
    ]
    audit_nodes_by_step = [
        row["node"] for row in sorted(audit_rows, key=lambda item: item["step_index"])
    ]
    sheet_rows = [payload for table, payload in client.inserts if table == "action_sheets"]

    assert response.document_markdown.startswith("# Media Plan")
    assert response.approval_id
    assert audit_nodes_by_step == ["brief", "research", "audience", "performance", "strategy"]
    assert sheet_rows[-1]["document_status"] == "pending"
