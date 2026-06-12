from mira_agent.graph.state import ResearchFinding
from mira_agent.integrations.crm import AudienceSegment
from mira_agent.services.expansion_hypothesis import (
    GENERIC_HYPOTHESIS_RE,
    build_expansion_audience_fit,
    build_expansion_hypothesis,
)


def test_build_expansion_hypothesis_uses_segment_token_and_research_title() -> None:
    hypothesis = build_expansion_hypothesis(
        "meta",
        [
            AudienceSegment(
                reference="crm:segment:company_size:51-200",
                label="Company Size: 51-200",
                count=7,
                dimension="company_size",
                value="51-200",
            )
        ],
        [
            ResearchFinding(
                title="Clarify.ai B2B paid social benchmark",
                url="https://example.com/clarify",
                highlights=["Meta can extend B2B demand beyond LinkedIn."],
            )
        ],
        "B2B marketers",
    )

    assert "51-200" in hypothesis
    assert "Clarify.ai" in hypothesis
    assert "meta" in hypothesis.lower()


def test_build_expansion_audience_fit_uses_crm_segment_reference() -> None:
    audience_fit = build_expansion_audience_fit(
        "meta",
        [
            AudienceSegment(
                reference="crm:segment:company_size:51-200",
                label="Company Size: 51-200",
                count=7,
                dimension="company_size",
                value="51-200",
            )
        ],
        "B2B marketers",
    )

    assert "crm:segment:company_size:51-200" in audience_fit
    assert "B2B marketers" in audience_fit


def test_generic_hypothesis_regex_matches_old_template() -> None:
    assert GENERIC_HYPOTHESIS_RE.search(
        "Test meta with controlled prospecting to prove qualified demand "
        "before releasing staged reserve."
    )
