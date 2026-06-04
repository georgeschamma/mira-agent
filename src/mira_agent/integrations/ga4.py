from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from datetime import datetime
from io import StringIO

from mira_agent.services.mmm import MIN_POINTS, ChannelObservations

CANONICAL_COLUMNS = (
    "date",
    "source",
    "medium",
    "channel",
    "cost",
    "conversions",
    "total_revenue",
)

COLUMN_ALIASES = {
    "date": "date",
    "session source": "source",
    "source": "source",
    "session medium": "medium",
    "medium": "medium",
    "session default channel group": "channel",
    "default channel group": "channel",
    "channel": "channel",
    "ad cost": "cost",
    "advertiser ad cost": "cost",
    "cost": "cost",
    "key events": "conversions",
    "conversions": "conversions",
    "total revenue": "total_revenue",
    "total_revenue": "total_revenue",
}


@dataclass(frozen=True)
class CsvParseWarning:
    row_number: int | None
    code: str
    message: str


@dataclass(frozen=True)
class ChannelPerformanceSummary:
    channel: str
    row_count: int
    total_cost: float
    total_response: float
    unique_spend_points: int
    sufficient_data: bool
    source_ref: str


@dataclass(frozen=True)
class Ga4ParseResult:
    observations: list[ChannelObservations]
    current_spend: dict[str, float]
    summaries: list[ChannelPerformanceSummary]
    warnings: list[CsvParseWarning] = field(default_factory=list)
    row_count: int = 0


class CsvParseError(ValueError):
    pass


def parse_ga4_csv(content: str | bytes) -> Ga4ParseResult:
    text = _decode(content)
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        raise CsvParseError("GA4 CSV is missing a header row.")

    field_map = _field_map(reader.fieldnames)
    missing = [column for column in CANONICAL_COLUMNS if column not in field_map.values()]
    if missing:
        raise CsvParseError(f"GA4 CSV is missing required columns: {', '.join(missing)}.")

    grouped: dict[str, list[tuple[float, float]]] = {}
    warnings: list[CsvParseWarning] = []
    row_count = 0

    for row_number, row in enumerate(reader, start=2):
        row_count += 1
        try:
            parsed = _parse_row(row=row, field_map=field_map)
        except CsvParseError as exc:
            warnings.append(
                CsvParseWarning(
                    row_number=row_number,
                    code="GA4_ROW_SKIPPED",
                    message=str(exc),
                )
            )
            continue

        grouped.setdefault(parsed.channel, []).append((parsed.cost, parsed.response))

    observations: list[ChannelObservations] = []
    current_spend: dict[str, float] = {}
    summaries: list[ChannelPerformanceSummary] = []
    for channel, points in sorted(grouped.items()):
        spend = [point[0] for point in points]
        response = [point[1] for point in points]
        unique_spend_points = len(set(spend))
        observations.append(ChannelObservations(channel=channel, spend=spend, response=response))
        current_spend[channel] = sum(spend)
        summaries.append(
            ChannelPerformanceSummary(
                channel=channel,
                row_count=len(points),
                total_cost=sum(spend),
                total_response=sum(response),
                unique_spend_points=unique_spend_points,
                sufficient_data=unique_spend_points >= MIN_POINTS,
                source_ref=f"ga4:channel:{_slug(channel)}",
            )
        )

    return Ga4ParseResult(
        observations=observations,
        current_spend=current_spend,
        summaries=summaries,
        warnings=warnings,
        row_count=row_count,
    )


@dataclass(frozen=True)
class _ParsedGa4Row:
    channel: str
    cost: float
    response: float


def _parse_row(row: dict[str, str], field_map: dict[str, str]) -> _ParsedGa4Row:
    raw_date = _value(row, field_map, "date")
    try:
        datetime.strptime(raw_date, "%Y-%m-%d")
    except ValueError as exc:
        raise CsvParseError(f"Invalid date {raw_date!r}; expected YYYY-MM-DD.") from exc

    source = _value(row, field_map, "source")
    medium = _value(row, field_map, "medium")
    channel = _value(row, field_map, "channel")
    if not source or not medium or not channel:
        raise CsvParseError("source, medium, and channel are required.")

    cost = _positive_float(_value(row, field_map, "cost"), "cost")
    conversions = _positive_float(_value(row, field_map, "conversions"), "conversions")
    total_revenue = _positive_float(_value(row, field_map, "total_revenue"), "total_revenue")
    response = total_revenue if total_revenue > 0 else conversions

    return _ParsedGa4Row(
        channel=f"{channel.strip()} | {source.strip()}/{medium.strip()}",
        cost=cost,
        response=response,
    )


def _field_map(fieldnames: list[str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for raw_name in fieldnames:
        canonical = COLUMN_ALIASES.get(_normalize_header(raw_name))
        if canonical and canonical not in resolved:
            resolved[raw_name] = canonical
    return resolved


def _value(row: dict[str, str], field_map: dict[str, str], canonical: str) -> str:
    for raw_name, mapped_name in field_map.items():
        if mapped_name == canonical:
            return (row.get(raw_name) or "").strip()
    return ""


def _positive_float(raw: str, field_name: str) -> float:
    try:
        value = float(raw or "0")
    except ValueError as exc:
        raise CsvParseError(f"Invalid {field_name} value {raw!r}.") from exc
    if not math.isfinite(value) or value < 0:
        raise CsvParseError(f"{field_name} must be a finite non-negative number.")
    return value


def _normalize_header(value: str) -> str:
    return value.strip().lower().replace("_", " ")


def _decode(content: str | bytes) -> str:
    if isinstance(content, bytes):
        return content.decode("utf-8-sig")
    return content


def _slug(value: str) -> str:
    return (
        value.lower()
        .replace("|", " ")
        .replace("/", " ")
        .replace("_", " ")
        .replace("-", " ")
        .strip()
        .replace(" ", "-")
    )
