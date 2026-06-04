import pytest

from mira_agent.integrations.crm import parse_crm_csv
from mira_agent.integrations.ga4 import CsvParseError


def test_parse_crm_valid_scoped_rows() -> None:
    csv_text = "\n".join(
        [
            "email,company,lifecycle_stage,industry,company_size",
            "a@example.com,Acme,lead,SaaS,51-200",
            "b@example.com,Bravo,customer,SaaS,201-500",
            "c@example.com,Charlie,lead,Services,51-200",
        ]
    )

    result = parse_crm_csv(csv_text)
    segments = {segment.reference: segment for segment in result.segments}

    assert result.row_count == 3
    assert result.pii_accessed is True
    assert segments["crm:segment:lifecycle_stage:lead"].count == 2
    assert segments["crm:segment:industry:saas"].count == 2


def test_parse_crm_missing_required_columns() -> None:
    csv_text = "\n".join(
        [
            "email,company,industry",
            "a@example.com,Acme,SaaS",
        ]
    )

    with pytest.raises(CsvParseError, match="lifecycle_stage"):
        parse_crm_csv(csv_text)


def test_parse_crm_rejects_protected_attributes() -> None:
    csv_text = "\n".join(
        [
            "email,company,lifecycle_stage,gender",
            "a@example.com,Acme,lead,unknown",
        ]
    )

    with pytest.raises(CsvParseError, match="protected attributes"):
        parse_crm_csv(csv_text)


def test_parse_crm_aggregates_without_exposing_emails() -> None:
    csv_text = "\n".join(
        [
            "email,company,lifecycle_stage",
            "private-person@example.com,Acme,lead",
            "other-person@example.com,Bravo,lead",
        ]
    )

    result = parse_crm_csv(csv_text)
    serialized = repr(result)

    assert "private-person@example.com" not in serialized
    assert "other-person@example.com" not in serialized
    assert result.segments[0].reference == "crm:segment:lifecycle_stage:lead"
    assert result.segments[0].count == 2
