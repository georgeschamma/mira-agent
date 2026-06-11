from __future__ import annotations

from mira_agent.integrations.crm import AudienceSegment
from mira_agent.services.audience_channel_map import map_audience_to_channels


def test_map_audience_leads() -> None:
    segments = [
        AudienceSegment(
            reference="crm:segment:lifecycle_stage:lead",
            label="Lifecycle Stage: lead",
            count=10,
            dimension="lifecycle_stage",
            value="lead",
        )
    ]
    hints = map_audience_to_channels(segments)
    assert "Prospecting: search + LinkedIn" in hints
    assert not any("Sparse segment" in h for h in hints)


def test_map_audience_customers() -> None:
    segments = [
        AudienceSegment(
            reference="crm:segment:lifecycle_stage:customer",
            label="Lifecycle Stage: customer",
            count=20,
            dimension="lifecycle_stage",
            value="customer",
        )
    ]
    hints = map_audience_to_channels(segments)
    assert "Exclude from cold prospecting; retarget only" in hints


def test_map_audience_saas_and_size() -> None:
    segments = [
        AudienceSegment(
            reference="crm:segment:industry:saas",
            label="Industry: SaaS",
            count=15,
            dimension="industry",
            value="SaaS",
        ),
        AudienceSegment(
            reference="crm:segment:company_size:51-200",
            label="Company Size: 51-200",
            count=12,
            dimension="company_size",
            value="51-200",
        ),
    ]
    hints = map_audience_to_channels(segments)
    assert "LinkedIn firmographic + search non-brand" in hints


def test_map_audience_sparse() -> None:
    segments = [
        AudienceSegment(
            reference="crm:segment:lifecycle_stage:lead",
            label="Lifecycle Stage: lead",
            count=3,
            dimension="lifecycle_stage",
            value="lead",
        )
    ]
    hints = map_audience_to_channels(segments)
    assert "Prospecting: search + LinkedIn" in hints
    assert any("Sparse segment 'Lifecycle Stage: lead': low confidence." in h for h in hints)
