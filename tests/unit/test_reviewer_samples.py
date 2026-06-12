from pathlib import Path

from mira_agent.integrations.crm import parse_crm_csv
from mira_agent.integrations.ga4 import parse_ga4_csv

SAMPLES_DIR = Path(__file__).parents[2] / "samples"


def test_reviewer_demo_csvs_parse_without_warnings() -> None:
    crm_result = parse_crm_csv((SAMPLES_DIR / "crm-demo.csv").read_text(encoding="utf-8"))
    ga4_result = parse_ga4_csv((SAMPLES_DIR / "ga4-demo.csv").read_text(encoding="utf-8"))

    assert crm_result.row_count == 12
    assert crm_result.warnings == []
    assert crm_result.segments
    assert ga4_result.row_count == 24
    assert ga4_result.warnings == []
    assert len(ga4_result.summaries) == 2
    assert all(summary.sufficient_data for summary in ga4_result.summaries)
