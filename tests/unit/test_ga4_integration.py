import pytest

from mira_agent.integrations.ga4 import CsvParseError, parse_ga4_csv


def test_parse_ga4_valid_canonical_csv() -> None:
    csv_text = "\n".join(
        [
            "date,source,medium,channel,cost,conversions,total_revenue",
            "2026-05-01,google,cpc,Paid Search,100,4,400",
            "2026-05-02,google,cpc,Paid Search,120,5,0",
        ]
    )

    result = parse_ga4_csv(csv_text)

    assert result.row_count == 2
    assert len(result.observations) == 1
    assert result.observations[0].channel == "Paid Search | google/cpc"
    assert result.observations[0].spend == [100.0, 120.0]
    assert result.observations[0].response == [400.0, 5.0]
    assert result.current_spend["Paid Search | google/cpc"] == 220.0


def test_parse_ga4_missing_required_columns() -> None:
    csv_text = "\n".join(
        [
            "date,source,medium,channel,conversions,total_revenue",
            "2026-05-01,google,cpc,Paid Search,4,400",
        ]
    )

    with pytest.raises(CsvParseError, match="cost"):
        parse_ga4_csv(csv_text)


def test_parse_ga4_invalid_rows_create_warnings() -> None:
    csv_text = "\n".join(
        [
            "date,source,medium,channel,cost,conversions,total_revenue",
            "2026/05/01,google,cpc,Paid Search,100,4,400",
            "2026-05-02,google,cpc,Paid Search,120,5,500",
            "2026-05-03,google,cpc,Paid Search,not-a-number,5,500",
        ]
    )

    result = parse_ga4_csv(csv_text)

    assert result.row_count == 3
    assert len(result.warnings) == 2
    assert result.observations[0].spend == [120.0]


def test_parse_ga4_sparse_channel_marked_insufficient() -> None:
    csv_text = "\n".join(
        [
            "date,source,medium,channel,cost,conversions,total_revenue",
            "2026-05-01,linkedin,paid,Paid Social,100,4,400",
            "2026-05-02,linkedin,paid,Paid Social,100,5,500",
            "2026-05-03,linkedin,paid,Paid Social,100,6,600",
        ]
    )

    result = parse_ga4_csv(csv_text)

    assert result.summaries[0].unique_spend_points == 1
    assert result.summaries[0].sufficient_data is False
