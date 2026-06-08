from typing import Any

import pytest

from mira_agent.exceptions import ApiError
from mira_agent.repositories.reports import fetch_action_sheet_report, fetch_audit_trace


class FakeRlsClient:
    def __init__(self, rows_by_table: dict[str, list[dict[str, Any]]]) -> None:
        self.rows_by_table = rows_by_table
        self.calls: list[dict[str, Any]] = []

    async def select(
        self,
        table: str,
        *,
        select: str = "*",
        filters: dict[str, str] | None = None,
        limit: int | None = None,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        self.calls.append(
            {
                "table": table,
                "select": select,
                "filters": filters,
                "limit": limit,
                "order": order,
            }
        )
        return self.rows_by_table.get(table, [])


def _brief() -> dict[str, Any]:
    return {
        "org_id": "11111111-1111-4111-8111-111111111111",
        "product": "MIRA",
        "audience": "B2B marketers",
        "channels": ["linkedin"],
        "budget": 1000,
        "goal": "book demos",
    }


def _recommendation() -> dict[str, Any]:
    return {
        "id": "rec_linkedin",
        "domain": "content",
        "finding": "Use proof-led LinkedIn content.",
        "source": "https://example.com/source",
        "effort": "low",
        "impact": "high",
        "action": "Publish a sourced proof post.",
        "needs_approval": True,
    }


@pytest.mark.asyncio
async def test_fetch_action_sheet_report_normalizes_recommendations_and_approvals() -> None:
    client = FakeRlsClient(
        {
            "action_sheets": [
                {
                    "id": "sheet_1",
                    "campaign_id": "campaign_1",
                    "run_id": "run_1",
                    "recommendations": [_recommendation()],
                    "model_used": "test-model",
                    "processing_ms": 1234,
                    "created_at": "2026-06-02T10:00:00Z",
                    "campaigns": {
                        "org_id": "11111111-1111-4111-8111-111111111111",
                        "brief": _brief(),
                    },
                }
            ],
            "action_sheet_approvals": [
                {
                    "recommendation_id": "rec_linkedin",
                    "status": "pending",
                    "approved_by": None,
                    "approved_at": None,
                    "created_at": "2026-06-02T10:01:00Z",
                }
            ],
        }
    )

    report = await fetch_action_sheet_report(
        client=client,  # type: ignore[arg-type]
        action_sheet_id="sheet_1",
    )

    assert report.action_sheet_id == "sheet_1"
    assert report.brief.product == "MIRA"
    assert report.recommendations[0].id == "rec_linkedin"
    assert report.recommendations[0].needs_approval is True
    assert report.approvals[0].recommendation_id == "rec_linkedin"
    assert report.approvals[0].status == "pending"
    assert client.calls[1]["order"] == "recommendation_id.asc"


@pytest.mark.asyncio
async def test_fetch_action_sheet_report_missing_sheet_raises_stable_code() -> None:
    client = FakeRlsClient({"action_sheets": []})

    with pytest.raises(ApiError) as exc_info:
        await fetch_action_sheet_report(
            client=client,  # type: ignore[arg-type]
            action_sheet_id="missing",
        )

    assert exc_info.value.code == "ACTION_SHEET_NOT_FOUND"
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_fetch_audit_trace_returns_step_index_order() -> None:
    client = FakeRlsClient(
        {
            "audit_log": [
                {
                    "id": "audit_2",
                    "campaign_id": "campaign_1",
                    "run_id": "run_1",
                    "step_index": 2,
                    "node": "content",
                    "summary": "Created recommendations.",
                    "source": "https://example.com/source",
                    "confidence": "high",
                    "pii_accessed": False,
                    "model_used": "test-model",
                    "created_at": "2026-06-02T10:02:00Z",
                },
                {
                    "id": "audit_0",
                    "campaign_id": "campaign_1",
                    "run_id": "run_1",
                    "step_index": 0,
                    "node": "router",
                    "summary": "Created campaign run.",
                    "source": "brief:product",
                    "confidence": "high",
                    "pii_accessed": False,
                    "model_used": "router",
                    "created_at": "2026-06-02T10:00:00Z",
                },
                {
                    "id": "audit_1",
                    "campaign_id": "campaign_1",
                    "run_id": "run_1",
                    "step_index": 1,
                    "node": "research",
                    "summary": "Collected Exa results.",
                    "source": "https://example.com/source",
                    "confidence": "medium",
                    "pii_accessed": False,
                    "model_used": "exa",
                    "created_at": "2026-06-02T10:01:00Z",
                },
            ],
        }
    )

    trace = await fetch_audit_trace(
        client=client,  # type: ignore[arg-type]
        run_id="run_1",
    )

    assert [row.node for row in trace.rows] == ["router", "research", "content"]
    assert client.calls[0]["order"] == "step_index.asc,created_at.asc"
