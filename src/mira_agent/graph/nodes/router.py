from __future__ import annotations

import time

from mira_agent.graph.context import MiraContext
from mira_agent.graph.state import MiraState
from mira_agent.repositories.campaigns import create_campaign_run, write_audit_row
from mira_agent.schemas.analyze import AnalyzeRequest


async def router_node(state: MiraState, context: MiraContext) -> MiraState:
    request = AnalyzeRequest.model_validate(state["request"])
    ids = await create_campaign_run(client=context.client, request=request, user=context.user)

    await write_audit_row(
        client=context.client,
        campaign_id=ids.campaign_id,
        run_id=ids.run_id,
        step_index=0,
        node="router",
        summary="Campaign brief accepted and analysis run started.",
        source="brief",
        confidence="high",
        model_used="none",
    )

    return {
        "campaign_id": ids.campaign_id,
        "run_id": ids.run_id,
        "findings": [],
        "recommendations": [],
        "errors": [],
        "model_used": context.settings.llm_model,
        "started_at": time.perf_counter(),
    }
