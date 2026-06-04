"""Unit tests for the deterministic MMM budget engine.

Fitting tests use synthetic data from a known curve and assert recovery within tolerance.
Marginal-ROI and allocation tests use hand-constructed curves so they do not depend on the
solver — they verify the math and the equal-marginal-ROI optimum directly.
"""

from __future__ import annotations

import numpy as np

from mira_agent.services.mmm import (
    AllocationPlan,
    ChannelCurve,
    ChannelObservations,
    allocation_plan_to_dict,
    fit_channel,
    fit_saturation_curve,
    insufficient_allocation,
    marginal_roi,
    optimize_allocation,
    response_at,
    saturation_fraction,
)


def _hill_curve(channel: str, vmax: float, k: float, a: float) -> ChannelCurve:
    return ChannelCurve(
        channel=channel,
        model="hill",
        params={"vmax": vmax, "k": k, "a": a},
        r_squared=1.0,
        n_points=20,
        confidence="high",
    )


# --- fitting ---------------------------------------------------------------


def test_fit_recovers_known_hill_params():
    spend = np.linspace(10, 500, 30)
    true = {"vmax": 1000.0, "k": 150.0, "a": 1.5}
    response = true["vmax"] * spend**true["a"] / (spend**true["a"] + true["k"] ** true["a"])
    curve = fit_saturation_curve(ChannelObservations("tv", list(spend), list(response)))

    assert curve is not None
    assert curve.model == "hill"
    assert curve.r_squared > 0.99
    assert abs(curve.params["k"] - true["k"]) / true["k"] < 0.1
    assert abs(curve.params["a"] - true["a"]) / true["a"] < 0.1


def test_fit_returns_none_when_too_few_points():
    obs = ChannelObservations("tv", [10, 20, 30], [1, 2, 3])
    assert fit_saturation_curve(obs) is None


def test_fit_channel_stamps_name():
    spend = np.linspace(10, 500, 30)
    response = 800 * np.log1p(0.01 * spend)
    curve = fit_channel(ChannelObservations("search", list(spend), list(response)))
    assert curve is not None
    assert curve.channel == "search"


# --- response & marginal roi ----------------------------------------------


def test_response_monotonic_increasing():
    curve = _hill_curve("tv", 1000, 150, 1.5)
    vals = [response_at(curve, s) for s in (0, 50, 150, 400, 1000)]
    assert all(b >= a for a, b in zip(vals, vals[1:], strict=False))


def test_response_at_half_saturation_is_half_vmax():
    curve = _hill_curve("tv", 1000, 150, 1.5)
    # At s == k the Hill function equals vmax/2 regardless of alpha.
    assert abs(response_at(curve, 150) - 500.0) < 1e-6


def test_marginal_roi_decreases_with_spend():
    curve = _hill_curve("tv", 1000, 150, 1.5)
    m_low = marginal_roi(curve, 200)
    m_high = marginal_roi(curve, 600)
    assert m_low > m_high > 0


def test_marginal_roi_scales_with_value():
    curve = _hill_curve("tv", 1000, 150, 1.5)
    base = marginal_roi(curve, 200, value_per_response=1.0)
    scaled = marginal_roi(curve, 200, value_per_response=2.5)
    assert abs(scaled - 2.5 * base) < 1e-6


def test_saturation_fraction_bounds_and_zones():
    curve = _hill_curve("tv", 1000, 150, 1.5)
    assert saturation_fraction(curve, 0) == 0.0
    assert 0.0 < saturation_fraction(curve, 150) < 1.0
    assert saturation_fraction(curve, 1e9) > 0.99


# --- allocation ------------------------------------------------------------


def test_allocation_conserves_budget():
    curves = [_hill_curve("tv", 1000, 150, 1.0), _hill_curve("search", 1000, 80, 1.0)]
    current = {"tv": 200.0, "search": 200.0}
    plan = optimize_allocation(curves, current, total_budget=400.0)
    total = sum(a.recommended_spend for a in plan.allocations)
    assert abs(total - 400.0) < 400.0 / 1000 + 1e-6


def test_allocation_respects_floor_and_cap():
    curves = [_hill_curve("tv", 1000, 150, 1.0), _hill_curve("search", 5000, 80, 1.0)]
    current = {"tv": 200.0, "search": 200.0}
    plan = optimize_allocation(curves, current, total_budget=400.0, floor_ratio=0.5, cap_ratio=2.0)
    by = {a.channel: a for a in plan.allocations}
    for ch in ("tv", "search"):
        assert by[ch].recommended_spend >= current[ch] * 0.5 - 1e-6
        assert by[ch].recommended_spend <= current[ch] * 2.0 + 1.0


def test_allocation_reports_budget_blocked_by_caps():
    curves = [_hill_curve("tv", 1000, 150, 1.0), _hill_curve("search", 1000, 80, 1.0)]
    current = {"tv": 100.0, "search": 100.0}

    plan = optimize_allocation(curves, current, total_budget=1000.0)

    assert sum(item.recommended_spend for item in plan.allocations) == 400.0
    assert plan.unallocated_budget == 600.0


def test_allocation_favors_less_saturated_channel():
    # search has a far higher ceiling -> steeper marginal returns -> should win budget.
    curves = [_hill_curve("tv", 1000, 150, 1.0), _hill_curve("search", 8000, 150, 1.0)]
    current = {"tv": 300.0, "search": 300.0}
    plan = optimize_allocation(curves, current, total_budget=600.0)
    by = {a.channel: a.recommended_spend for a in plan.allocations}
    assert by["search"] > by["tv"]


def test_allocation_equalizes_marginal_roi_at_optimum():
    curves = [_hill_curve("tv", 2000, 150, 1.0), _hill_curve("search", 3000, 200, 1.0)]
    current = {"tv": 300.0, "search": 300.0}
    plan = optimize_allocation(curves, current, total_budget=600.0, cap_ratio=5.0, steps=2000)
    mrois = [a.marginal_roi for a in plan.allocations]
    # interior optimum -> marginal ROIs converge close together
    assert max(mrois) - min(mrois) < 0.05 * max(mrois)


def test_allocation_lifts_total_response():
    curves = [_hill_curve("tv", 1000, 150, 1.0), _hill_curve("search", 8000, 150, 1.0)]
    current = {"tv": 500.0, "search": 100.0}  # deliberately mis-allocated
    plan = optimize_allocation(curves, current, total_budget=600.0)
    assert plan.projected_total_response >= plan.baseline_total_response


def test_empty_curves_returns_empty_plan():
    plan = optimize_allocation([], {}, total_budget=1000.0)
    assert plan.allocations == []
    assert plan.projected_total_response == 0.0


def test_floor_overflow_does_not_exceed_total_budget():
    curves = [_hill_curve("tv", 1000, 150, 1.0), _hill_curve("search", 1000, 80, 1.0)]
    current = {"tv": 1000.0, "search": 1000.0}
    plan = optimize_allocation(curves, current, total_budget=500.0, floor_ratio=0.8)
    total = sum(a.recommended_spend for a in plan.allocations)

    assert abs(total - 500.0) < 1e-6


def test_insufficient_allocation_serializes_without_non_finite_values():
    allocation = insufficient_allocation("paid_social", current_spend=250.0)
    safe = allocation_plan_to_dict(
        AllocationPlan(
            allocations=[allocation],
            total_budget=250.0,
            baseline_total_response=0.0,
            projected_total_response=0.0,
        )
    )

    assert safe["allocations"][0]["projected_response"] is None
    assert safe["allocations"][0]["marginal_roi"] is None
