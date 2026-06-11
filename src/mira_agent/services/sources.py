from __future__ import annotations

ALLOWED_SOURCE_PREFIXES = ("https://", "brief:", "crm:segment:", "ga4:", "performance:")


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
