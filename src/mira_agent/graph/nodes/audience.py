from __future__ import annotations

from mira_agent.graph.context import MiraContext
from mira_agent.graph.state import MiraMediaPlanState, NodeError
from mira_agent.integrations.crm import parse_crm_csv
from mira_agent.integrations.ga4 import CsvParseError
from mira_agent.repositories.campaigns import write_audit_row
from mira_agent.schemas.media_plan import MediaPlanGraphRequest
from mira_agent.services.audience_channel_map import map_audience_to_channels


async def audience_node(state: MiraMediaPlanState, context: MiraContext) -> MiraMediaPlanState:
    request = MediaPlanGraphRequest.model_validate(state["media_input"])
    campaign_id = state["campaign_id"]
    run_id = state["run_id"]

    try:
        result = parse_crm_csv(request.crm_csv_text)
    except CsvParseError as exc:
        await write_audit_row(
            client=context.client,
            campaign_id=campaign_id,
            run_id=run_id,
            step_index=2,
            node="audience",
            summary="CRM audience parsing failed.",
            source="crm:csv",
            confidence="low",
            model_used="none",
            pii_accessed=True,
        )
        return {
            "audience_segments": [],
            "warnings": [],
            "crm_warnings": [],
            "crm_row_count": 0,
            "errors": [
                NodeError(node="audience", code="CRM_PARSE_FAILED", message=str(exc)),
            ],
        }

    confidence = "medium" if result.segments else "low"
    await write_audit_row(
        client=context.client,
        campaign_id=campaign_id,
        run_id=run_id,
        step_index=2,
        node="audience",
        summary=f"Parsed {len(result.segments)} aggregate CRM audience segments.",
        source="crm:segment:lifecycle_stage",
        confidence=confidence,
        model_used="none",
        pii_accessed=True,
    )

    hints = map_audience_to_channels(result.segments)

    return {
        "audience_segments": result.segments,
        "audience_channel_hints": hints,
        "warnings": [warning.message for warning in result.warnings],
        "crm_warnings": result.warnings,
        "crm_row_count": result.row_count,
        "errors": [],
    }

