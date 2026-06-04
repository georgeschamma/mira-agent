from __future__ import annotations

import re
import time

from mira_agent.graph.context import MiraContext
from mira_agent.graph.state import MiraMediaPlanState, ParsedMediaBrief
from mira_agent.repositories.campaigns import create_campaign_run, write_audit_row
from mira_agent.schemas.analyze import AnalyzeRequest
from mira_agent.schemas.media_plan import MediaPlanGraphRequest


async def brief_node(state: MiraMediaPlanState, context: MiraContext) -> MiraMediaPlanState:
    request = MediaPlanGraphRequest.model_validate(state["request"])
    parsed = parse_media_plan_brief(org_id=request.org_id, brief=request.brief)
    analyze_request = AnalyzeRequest(
        org_id=parsed.org_id,
        product=parsed.product,
        audience=parsed.audience,
        channels=parsed.channels,
        budget=parsed.budget,
        goal=parsed.goal,
    )
    ids = await create_campaign_run(
        client=context.client,
        request=analyze_request,
        user=context.user,
    )

    await write_audit_row(
        client=context.client,
        campaign_id=ids.campaign_id,
        run_id=ids.run_id,
        step_index=0,
        node="brief",
        summary="Free-text brief parsed and media-plan run started.",
        source="brief:raw",
        confidence="medium",
        model_used="none",
    )

    return {
        "request": analyze_request.model_dump(),
        "media_input": request.model_dump(),
        "campaign_id": ids.campaign_id,
        "run_id": ids.run_id,
        "parsed_brief": parsed,
        "findings": [],
        "audience_segments": [],
        "channel_summaries": [],
        "allocations": [],
        "errors": [],
        "warnings": [],
        "crm_warnings": [],
        "ga4_warnings": [],
        "model_used": context.settings.llm_model,
        "started_at": time.perf_counter(),
    }


def parse_media_plan_brief(*, org_id: str, brief: str) -> ParsedMediaBrief:
    product = _field_value(brief, "product") or _field_value(brief, "company") or "Media plan"
    audience = _field_value(brief, "audience") or _field_value(brief, "target") or "target audience"
    channels_raw = _field_value(brief, "channels") or _field_value(brief, "channel") or "paid media"
    goal = _field_value(brief, "goal") or _field_value(brief, "objective") or "improve performance"
    budget_raw = _field_value(brief, "budget") or brief

    channels = [item.strip() for item in re.split(r"[,/]", channels_raw) if item.strip()]
    budget_match = re.search(r"(\d[\d,]*)", budget_raw)
    budget = int(budget_match.group(1).replace(",", "")) if budget_match else 0

    return ParsedMediaBrief(
        org_id=org_id,
        product=product.strip(),
        audience=audience.strip(),
        channels=channels or ["paid media"],
        budget=budget,
        goal=goal.strip(),
        raw_brief=brief,
    )


def _field_value(text: str, field_name: str) -> str | None:
    pattern = re.compile(rf"^{field_name}\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(text)
    return match.group(1).strip() if match else None
