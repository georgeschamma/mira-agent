from __future__ import annotations

from dataclasses import dataclass

from mira_agent.services.allocation_policy import ExpansionAllocation


@dataclass(frozen=True)
class WaterfallRow:
    label: str
    amount: float
    category: str
    audit_ref: str


def build_budget_waterfall(
    *,
    brief_budget: float,
    fitted_total: float,
    expansion_allocations: list[ExpansionAllocation],
    reserve_pool: float,
) -> list[WaterfallRow]:
    rows: list[WaterfallRow] = []
    if fitted_total > 0.01:
        rows.append(
            WaterfallRow(
                label="Fitted channels (GA4-backed)",
                amount=fitted_total,
                category="fitted",
                audit_ref="performance:allocation",
            )
        )

    for allocation in expansion_allocations:
        if allocation.phase1_test_budget > 0.01:
            rows.append(
                WaterfallRow(
                    label=f"Phase-1 test - {allocation.channel}",
                    amount=allocation.phase1_test_budget,
                    category="phase1_test",
                    audit_ref="performance:allocation",
                )
            )
        if allocation.staged_reserve > 0.01:
            rows.append(
                WaterfallRow(
                    label=f"Staged reserve - {allocation.channel}",
                    amount=allocation.staged_reserve,
                    category="staged_reserve",
                    audit_ref="performance:allocation",
                )
            )

    policy_reserve = max(reserve_pool, 0.0)
    if brief_budget > 0:
        assigned = sum(row.amount for row in rows)
        policy_reserve = max(brief_budget - assigned, 0.0)

    if policy_reserve > 0.01:
        rows.append(
            WaterfallRow(
                label="Policy reserve pool",
                amount=policy_reserve,
                category="policy_reserve",
                audit_ref="performance:allocation",
            )
        )

    return rows


def describe_budget_waterfall(rows: list[WaterfallRow]) -> list[str]:
    return [
        f"{row.label}: {_money(row.amount)} ({row.category}, {row.audit_ref})."
        for row in rows
    ]


def _money(value: float) -> str:
    return f"${value:,.0f}"
