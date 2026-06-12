from mira_agent.services.allocation_policy import ExpansionAllocation
from mira_agent.services.budget_waterfall import build_budget_waterfall


def test_waterfall_sums_to_brief_budget_for_10k_growth() -> None:
    rows = build_budget_waterfall(
        brief_budget=10_000,
        fitted_total=1_740,
        expansion_allocations=[
            ExpansionAllocation(
                channel="meta",
                phase1_test_budget=3_300,
                staged_reserve=200,
                weight_notes="Expansion allocation for meta.",
            ),
            ExpansionAllocation(
                channel="tiktok",
                phase1_test_budget=3_300,
                staged_reserve=200,
                weight_notes="Expansion allocation for tiktok.",
            ),
        ],
        reserve_pool=1_260,
    )

    assert sum(row.amount for row in rows) == 10_000
    assert any("meta" in row.label.lower() for row in rows)
    assert [row.category for row in rows] == [
        "fitted",
        "phase1_test",
        "staged_reserve",
        "phase1_test",
        "staged_reserve",
        "policy_reserve",
    ]


def test_waterfall_uses_policy_reserve_to_conserve_budget() -> None:
    rows = build_budget_waterfall(
        brief_budget=1_000,
        fitted_total=600,
        expansion_allocations=[],
        reserve_pool=0,
    )

    assert rows[-1].label == "Policy reserve pool"
    assert rows[-1].amount == 400
    assert sum(row.amount for row in rows) == 1_000
