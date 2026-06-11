from __future__ import annotations

from mira_agent.graph.context import MiraContext
from mira_agent.graph.state import MiraMediaPlanState
from mira_agent.repositories.campaigns import finish_campaign_run, write_audit_row

ALLOWED_SOURCE_PREFIXES = ("https://", "brief:", "crm:segment:", "ga4:", "performance:")


async def critic_node(state: MiraMediaPlanState, context: MiraContext) -> MiraMediaPlanState:
    campaign_id = state["campaign_id"]
    run_id = state["run_id"]
    strategic_brief = state.get("strategic_brief")
    allocations = state.get("allocations", [])
    document_metadata = state.get("document_metadata", {})

    claims = document_metadata.get("source_claims", [])
    expansion_budget = state.get("expansion_budget", 0.0)

    remediations = []

    # Check 1: Recommends scaling channel in do_not_scale
    if strategic_brief:
        do_not_scale_channels = strategic_brief.do_not_scale or []
        for a in allocations:
            clean_ch = a.channel.replace("|", "/").strip()
            is_dns = any(
                clean_ch.lower() in dns.lower()
                or dns.lower() in clean_ch.lower()
                or a.channel.lower() in dns.lower()
                for dns in do_not_scale_channels
            )
            if is_dns and a.delta > 0.5:
                remediations.append(
                    f"Contradiction: Recommended spend increases on "
                    f"channel '{a.channel}' by {a.delta:,.0f}, "
                    f"but it is marked as DO NOT SCALE in do_not_scale."
                )

    # Check 2: expansion_budget > 0 but no expansion tests
    if expansion_budget > 0.01:
        tests = strategic_brief.expansion_tests if strategic_brief else []
        if not tests:
            remediations.append(
                f"Contradiction: Expansion budget of ${expansion_budget:,.2f} is available, "
                f"but no expansion tests were defined."
            )

    # Check 3: Claims missing required source prefixes
    for claim in claims:
        source = claim.get("source", "")
        if not source.startswith(ALLOWED_SOURCE_PREFIXES):
            remediations.append(
                f"Claim validation failure: Source '{source}' does "
                f"not start with a valid prefix: {ALLOWED_SOURCE_PREFIXES}."
            )

    # Check 4: Executive summary contradicts table (cut/reduce CAC but delta positive)
    if strategic_brief and strategic_brief.planning_mode == "efficiency":
        total_delta = sum(a.delta for a in allocations)
        if total_delta > 0.5:
            remediations.append(
                "Contradiction: Planning mode is 'efficiency' (reduce spend), "
                f"but total recommended budget delta is positive (+${total_delta:,.2f})."
            )

    failed = len(remediations) > 0
    retries = state.get("strategy_retries", 0)

    if failed and retries <= 1:
        # Retry strategy node with remediation context
        await write_audit_row(
            client=context.client,
            campaign_id=campaign_id,
            run_id=run_id,
            step_index=6,
            node="critic",
            summary=(
                f"Critic node detected contradictions: {'; '.join(remediations)}. "
                "Retrying strategy node."
            ),
            source="performance:allocation",
            confidence="low",
            model_used="none",
        )
        return {
            "critic_failed": True,
            "strategy_remediation": "; ".join(remediations),
        }

    # Save final campaign run status
    status = "partial" if failed or state.get("errors") else "done"
    await finish_campaign_run(
        client=context.client,
        run_id=run_id,
        status=status,
    )

    summary = (
        "Critic node passed plan validation."
        if not failed
        else (
            f"Critic node failed plan validation: {'; '.join(remediations)}. "
            "No retries left, saving as partial."
        )
    )
    confidence = "high" if not failed and not state.get("errors") else "low"
    await write_audit_row(
        client=context.client,
        campaign_id=campaign_id,
        run_id=run_id,
        step_index=6,
        node="critic",
        summary=summary,
        source="performance:allocation",
        confidence=confidence,
        model_used="none",
    )

    return {
        "critic_failed": failed,
        "strategy_remediation": "; ".join(remediations) if failed else "",
    }
