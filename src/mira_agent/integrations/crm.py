from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from io import StringIO

from mira_agent.integrations.ga4 import CsvParseError, CsvParseWarning

REQUIRED_COLUMNS = ("email", "company", "lifecycle_stage")
OPTIONAL_SEGMENT_COLUMNS = ("industry", "company_size", "region", "country")
ALLOWED_COLUMNS = set(REQUIRED_COLUMNS + OPTIONAL_SEGMENT_COLUMNS)
PROTECTED_COLUMNS = {
    "age",
    "gender",
    "sex",
    "race",
    "ethnicity",
    "religion",
    "disability",
    "sexual_orientation",
    "national_origin",
    "marital_status",
    "veteran_status",
    "health_status",
}


@dataclass(frozen=True)
class AudienceSegment:
    reference: str
    label: str
    count: int
    dimension: str
    value: str


@dataclass(frozen=True)
class CrmParseResult:
    segments: list[AudienceSegment]
    row_count: int
    warnings: list[CsvParseWarning] = field(default_factory=list)
    pii_accessed: bool = True


def parse_crm_csv(content: str | bytes) -> CrmParseResult:
    text = _decode(content)
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        raise CsvParseError("CRM CSV is missing a header row.")

    normalized_headers = {_normalize_header(header): header for header in reader.fieldnames}
    protected = sorted(set(normalized_headers) & PROTECTED_COLUMNS)
    if protected:
        raise CsvParseError(f"CRM CSV contains protected attributes: {', '.join(protected)}.")

    missing = [column for column in REQUIRED_COLUMNS if column not in normalized_headers]
    if missing:
        raise CsvParseError(f"CRM CSV is missing required columns: {', '.join(missing)}.")

    unexpected = sorted(set(normalized_headers) - ALLOWED_COLUMNS)
    if unexpected:
        raise CsvParseError(f"CRM CSV contains unsupported columns: {', '.join(unexpected)}.")

    row_count = 0
    warnings: list[CsvParseWarning] = []
    segment_counts: dict[tuple[str, str], int] = {}
    for row_number, row in enumerate(reader, start=2):
        row_count += 1
        lifecycle_stage = _row_value(row, normalized_headers, "lifecycle_stage")
        if not lifecycle_stage:
            warnings.append(
                CsvParseWarning(
                    row_number=row_number,
                    code="CRM_ROW_SKIPPED",
                    message="Missing lifecycle_stage.",
                )
            )
            continue

        _increment(segment_counts, "lifecycle_stage", lifecycle_stage)
        for column in OPTIONAL_SEGMENT_COLUMNS:
            value = _row_value(row, normalized_headers, column)
            if value:
                _increment(segment_counts, column, value)

    segments = [
        AudienceSegment(
            reference=f"crm:segment:{dimension}:{_slug(value)}",
            label=f"{dimension.replace('_', ' ').title()}: {value}",
            count=count,
            dimension=dimension,
            value=value,
        )
        for (dimension, value), count in sorted(segment_counts.items())
    ]

    return CrmParseResult(
        segments=segments,
        row_count=row_count,
        warnings=warnings,
        pii_accessed=True,
    )


def _increment(counts: dict[tuple[str, str], int], dimension: str, value: str) -> None:
    cleaned = value.strip()
    if not cleaned:
        return
    key = (dimension, cleaned)
    counts[key] = counts.get(key, 0) + 1


def _row_value(row: dict[str, str], headers: dict[str, str], canonical: str) -> str:
    raw_header = headers.get(canonical)
    if not raw_header:
        return ""
    return (row.get(raw_header) or "").strip()


def _normalize_header(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _decode(content: str | bytes) -> str:
    if isinstance(content, bytes):
        return content.decode("utf-8-sig")
    return content


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "unknown"
