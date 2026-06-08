from mira_agent.graph.nodes.brief import parse_media_plan_brief


def test_brief_without_budget_does_not_use_product_version() -> None:
    parsed = parse_media_plan_brief(
        org_id="org_1",
        brief="Product: MIRA 2.0\nAudience: B2B marketers\nGoal: book demos",
    )

    assert parsed.budget == 0


def test_brief_parses_budget_from_prose() -> None:
    parsed = parse_media_plan_brief(
        org_id="org_1",
        brief="We need a MIRA media plan. The budget is $1,500 for B2B demo generation.",
    )

    assert parsed.budget == 1500
