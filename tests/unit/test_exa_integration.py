from types import SimpleNamespace

from mira_agent.integrations.exa import normalize_search_response


def test_normalize_search_response_from_dict_payload() -> None:
    response = {
        "results": [
            {
                "title": "B2B marketing benchmarks",
                "url": "https://example.com/benchmarks",
                "highlights": ["LinkedIn conversion rates vary by audience."],
                "publishedDate": "2026-05-01",
            }
        ]
    }

    findings = normalize_search_response(response)

    assert len(findings) == 1
    assert findings[0].title == "B2B marketing benchmarks"
    assert findings[0].url == "https://example.com/benchmarks"
    assert findings[0].highlights == ["LinkedIn conversion rates vary by audience."]
    assert findings[0].published_date == "2026-05-01"


def test_normalize_search_response_skips_results_without_url() -> None:
    response = {"results": [{"title": "Missing URL", "highlights": ["Not usable."]}]}

    findings = normalize_search_response(response)

    assert findings == []


def test_normalize_search_response_from_object_payload() -> None:
    response = SimpleNamespace(
        results=[
            SimpleNamespace(
                title="Campaign analysis",
                url="https://example.com/campaign",
                highlights=[{"text": "Marketing teams need tighter proof loops."}],
                published_date=None,
            )
        ]
    )

    findings = normalize_search_response(response)

    assert findings[0].highlights == ["Marketing teams need tighter proof loops."]
