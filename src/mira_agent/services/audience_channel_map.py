from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mira_agent.integrations.crm import AudienceSegment


def map_audience_to_channels(segments: list[AudienceSegment]) -> list[str]:
    hints: list[str] = []

    # Map segment dimensions/values
    has_lead = False
    has_customer = False
    has_saas = False
    has_size_51_200 = False

    for segment in segments:
        dim = segment.dimension.lower() if segment.dimension else ""
        val = segment.value.lower() if segment.value else ""
        
        # Sparse segment check
        if segment.count < 5:
            hints.append(f"Sparse segment '{segment.label}': low confidence.")

        if dim == "lifecycle_stage":
            if val == "lead":
                has_lead = True
            elif val == "customer":
                has_customer = True
        elif dim == "industry" and val == "saas":
            has_saas = True
        elif dim == "company_size" and val == "51-200":
            has_size_51_200 = True

    if has_lead:
        hints.append("Prospecting: search + LinkedIn")
    if has_customer:
        hints.append("Exclude from cold prospecting; retarget only")
    if has_saas and has_size_51_200:
        hints.append("LinkedIn firmographic + search non-brand")

    return hints
