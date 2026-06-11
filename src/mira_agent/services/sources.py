from __future__ import annotations

from collections.abc import Mapping
from typing import Any

ALLOWED_SOURCE_PREFIXES = ("https://", "brief:", "crm:segment:", "ga4:", "performance:")
FIXED_SOURCE_REFS = frozenset(
    {
        "performance:allocation",
        "brief:raw",
        "brief:channels",
        "brief:audience",
        "brief:budget",
        "brief:goal",
    }
)


def validate_source_ref(value: str) -> str:
    source = value.strip()
    if source.startswith(ALLOWED_SOURCE_PREFIXES):
        return source
    allowed = ", ".join(ALLOWED_SOURCE_PREFIXES)
    raise ValueError(
        "Use a source reference only, not prose. "
        f"Source must start with one of: {allowed}. "
        "Examples: brief:channels, performance:allocation, "
        "crm:segment:lifecycle_stage:lead, ga4:channel:paid-search, "
        "or https://example.com/source."
    )


def build_source_whitelist(state: Mapping[str, Any]) -> set[str]:
    allowed_refs = set(FIXED_SOURCE_REFS)
    for finding in state.get("findings", []):
        _add_value(allowed_refs, finding, "url")
    for summary in state.get("channel_summaries", []):
        _add_value(allowed_refs, summary, "source_ref")
    for segment in state.get("audience_segments", []):
        _add_value(allowed_refs, segment, "reference")
    return allowed_refs


def validate_source_ref_against_whitelist(value: str, allowed_refs: set[str]) -> str:
    source = validate_source_ref(value)
    if source in allowed_refs:
        return source
    allowed = ", ".join(sorted(allowed_refs))
    if source.startswith("https://"):
        raise ValueError(
            f"Unsupported source '{source}'. HTTPS sources must be one of the actual "
            f"research finding URLs. Allowed sources: {allowed}."
        )
    raise ValueError(
        f"Unsupported source '{source}'. Non-HTTPS sources must match the allowed source "
        f"list exactly. Allowed sources: {allowed}."
    )


def source_ref_is_allowed(value: str, allowed_refs: set[str]) -> bool:
    try:
        validate_source_ref_against_whitelist(value, allowed_refs)
    except ValueError:
        return False
    return True


def _add_value(allowed_refs: set[str], item: object, field: str) -> None:
    value: object
    if isinstance(item, Mapping):
        value = item.get(field, "")
    else:
        value = getattr(item, field, "")
    if isinstance(value, str) and value:
        allowed_refs.add(value)
