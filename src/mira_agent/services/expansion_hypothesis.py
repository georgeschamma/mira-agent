from __future__ import annotations

import re
from urllib.parse import urlparse

from mira_agent.graph.state import ResearchFinding
from mira_agent.integrations.crm import AudienceSegment
from mira_agent.services.allocation_policy import _normalized_channel_name

GENERIC_HYPOTHESIS_RE = re.compile(
    r"controlled prospecting to prove qualified demand",
    re.I,
)


def build_expansion_hypothesis(
    channel: str,
    segments: list[AudienceSegment],
    findings: list[ResearchFinding],
    brief_audience: str,
) -> str:
    channel_name = _normalized_channel_name(channel) or channel.lower().strip()
    segment_phrase = _segment_phrase(segments)
    finding = _matching_finding(channel_name, findings)
    if finding is not None:
        source_hint = _finding_hint(finding)
        return (
            f"Run {channel_name} prospecting to {segment_phrase}; "
            f"{source_hint} suggests {channel_name} can expand qualified demand."
        )[:220]
    return (
        f"Run {channel_name} prospecting to {segment_phrase} from the {brief_audience} audience "
        f"to validate lower-cost qualified demand."
    )[:220]


def build_expansion_audience_fit(
    channel: str,
    segments: list[AudienceSegment],
    brief_audience: str,
) -> str:
    segment_phrase = _segment_phrase(segments)
    if segments:
        return (
            f"Targets {segment_phrase} from CRM and aligns to {brief_audience}."
        )[:220]
    return f"Matches the requested audience: {brief_audience}."[:220]


def _segment_phrase(segments: list[AudienceSegment]) -> str:
    if not segments:
        return "the highest-priority CRM segment"
    top = sorted(segments, key=lambda item: item.count, reverse=True)[0]
    label = top.label.replace("Lifecycle Stage: ", "").replace("Company Size: ", "")
    return f"{label} leads ({top.reference})"


def _matching_finding(channel: str, findings: list[ResearchFinding]) -> ResearchFinding | None:
    aliases = {
        "meta": {"meta", "facebook", "instagram"},
        "x": {"x", "twitter"},
    }
    terms = aliases.get(channel, {channel})
    for finding in findings:
        haystack = " ".join([finding.title, *finding.highlights]).lower()
        if any(term in haystack for term in terms):
            return finding
    return findings[0] if findings else None


def _finding_hint(finding: ResearchFinding) -> str:
    host = urlparse(finding.url).netloc.replace("www.", "")
    title = finding.title.strip()
    if title:
        return title[:60]
    return host[:40] or "Research"
