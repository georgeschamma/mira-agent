import pytest
from pydantic_ai.models.test import TestModel

from mira_agent.config import Settings
from mira_agent.exceptions import ApiError
from mira_agent.graph.context import MiraContext
from mira_agent.graph.nodes.content import assert_valid_sources, generate_recommendations
from mira_agent.graph.state import ResearchFinding
from mira_agent.schemas.analyze import Recommendation
from mira_agent.schemas.auth import CurrentUser


class DummyResearchClient:
    async def search(self, query: str, *, num_results: int) -> list[ResearchFinding]:
        return []


class DummyRlsClient:
    pass


def _recommendation(source: str) -> Recommendation:
    return Recommendation(
        id="rec_1",
        domain="research",
        finding="Use proof points from the strongest source.",
        source=source,
        effort="low",
        impact="high",
        action="Turn the proof point into a LinkedIn test.",
        needs_approval=True,
    )


def test_source_guard_rejects_model_only_source() -> None:
    with pytest.raises(ApiError) as exc_info:
        assert_valid_sources([_recommendation("llm")])

    assert exc_info.value.code == "UNSOURCED_RECOMMENDATION"


def test_source_guard_accepts_url_and_brief_sources() -> None:
    assert_valid_sources([_recommendation("https://example.com/source")])
    assert_valid_sources([_recommendation("brief:goal")])


@pytest.mark.asyncio
async def test_generate_recommendations_normalizes_source_and_high_approval() -> None:
    model = TestModel(
        custom_output_args={
            "recommendations": [
                {
                    "id": "",
                    "domain": "content",
                    "finding": "Use market benchmarks in the launch post.",
                    "source": "B2B benchmark report",
                    "effort": "low",
                    "impact": "high",
                    "action": "Publish a sourced LinkedIn post.",
                    "needs_approval": False,
                },
                {
                    "id": "rec_goal",
                    "domain": "research",
                    "finding": "Tie the CTA to demo bookings.",
                    "source": "brief:goal",
                    "effort": "low",
                    "impact": "medium",
                    "action": "Make the CTA explicit.",
                    "needs_approval": True,
                },
            ]
        }
    )
    context = MiraContext(
        client=DummyRlsClient(),  # type: ignore[arg-type]
        user=CurrentUser(id="user_1", token="jwt"),
        settings=Settings(llm_model="test-model", llm_api_key="test", exa_api_key="test"),
        research_client=DummyResearchClient(),
        model=model,
    )
    state = {
        "request": {
            "org_id": "11111111-1111-4111-8111-111111111111",
            "product": "MIRA",
            "audience": "B2B marketers",
            "channels": ["linkedin"],
            "budget": 1000,
            "goal": "book demos",
        },
        "user_id": "user_1",
        "findings": [
            ResearchFinding(
                title="B2B benchmark report",
                url="https://example.com/benchmarks",
                highlights=["Benchmarks help marketers prioritize channels."],
            )
        ],
    }

    recommendations = await generate_recommendations(state, context)

    assert recommendations[0].id == "rec_1"
    assert recommendations[0].source == "https://example.com/benchmarks"
    assert recommendations[0].needs_approval is True
    assert recommendations[1].needs_approval is False
