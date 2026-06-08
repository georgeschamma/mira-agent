from typing import Any

import pytest

from mira_agent.config import Settings
from mira_agent.graph.context import MiraContext
from mira_agent.graph.nodes.performance import performance_node
from mira_agent.graph.state import ParsedMediaBrief
from mira_agent.schemas.auth import CurrentUser


class FakeRlsClient:
    def __init__(self) -> None:
        self.inserts: list[tuple[str, dict[str, Any]]] = []

    async def insert(self, table: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        self.inserts.append((table, payload))
        return [payload]


class UnusedResearchClient:
    async def search(self, query: str, *, num_results: int):
        return []


@pytest.mark.asyncio
async def test_performance_node_marks_sparse_ga4_as_insufficient_data() -> None:
    client = FakeRlsClient()
    context = MiraContext(
        client=client,  # type: ignore[arg-type]
        user=CurrentUser(id="user_1", token="jwt"),
        settings=Settings(llm_model="test-model", llm_api_key="test", exa_api_key="test"),
        research_client=UnusedResearchClient(),
        model=None,
    )
    state = {
        "campaign_id": "campaign_1",
        "run_id": "run_1",
        "parsed_brief": ParsedMediaBrief(
            org_id="org_1",
            product="MIRA",
            audience="B2B marketers",
            channels=["linkedin"],
            budget=300,
            goal="book demos",
            raw_brief="Budget: 300",
        ),
        "media_input": {
            "org_id": "org_1",
            "brief": "Budget: 300",
            "crm_csv_text": "",
            "crm_filename": "crm.csv",
            "ga4_csv_text": "\n".join(
                [
                    "date,source,medium,channel,cost,conversions,total_revenue",
                    "2026-05-01,linkedin,paid,Paid Social,100,4,400",
                    "2026-05-02,linkedin,paid,Paid Social,100,5,500",
                    "2026-05-03,linkedin,paid,Paid Social,100,6,600",
                ]
            ),
            "ga4_filename": "ga4.csv",
        },
    }

    result = await performance_node(state, context)  # type: ignore[arg-type]

    assert result["allocations"][0].zone == "insufficient_data"
    assert result["allocations"][0].projected_response is None
    assert result["ga4_row_count"] == 3
    audit_rows = [payload for table, payload in client.inserts if table == "audit_log"]
    assert audit_rows[0]["node"] == "performance"
    assert audit_rows[0]["step_index"] == 3
