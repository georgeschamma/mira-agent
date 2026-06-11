"""Deterministic MMM-logic budget engine.

Pure functions only — no LLM, no I/O. Fits a saturation curve per channel, computes
marginal ROI, and reallocates a fixed budget so marginal ROI equalises across channels
(the mathematical optimum). Labelled honestly as a heuristic response-curve fit, not a
Bayesian MMM.

Models:
  Hill (primary):  response(s) = vmax * s**a / (s**a + k**a)
  Log  (fallback): response(s) = c * ln(1 + d*s)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy.optimize import curve_fit

CurveModel = Literal["hill", "log"]
Confidence = Literal["high", "medium", "low"]
Zone = Literal["underspend", "optimal", "saturated", "insufficient_data"]

MIN_POINTS = 8
_TINY = 1e-9


@dataclass(frozen=True)
class ChannelObservations:
    """Historical (spend, response) pairs for one channel."""

    channel: str
    spend: list[float]
    response: list[float]


@dataclass(frozen=True)
class ChannelCurve:
    """A fitted saturation curve for one channel."""

    channel: str
    model: CurveModel
    params: dict[str, float]
    r_squared: float
    n_points: int
    confidence: Confidence


@dataclass(frozen=True)
class ChannelAllocation:
    channel: str
    current_spend: float
    recommended_spend: float
    delta: float
    projected_response: float | None
    marginal_roi: float | None
    zone: Zone


@dataclass(frozen=True)
class AllocationPlan:
    allocations: list[ChannelAllocation]
    total_budget: float
    baseline_total_response: float
    projected_total_response: float
    unallocated_budget: float = 0.0


# ---------------------------------------------------------------------------
# Curve models
# ---------------------------------------------------------------------------


def _hill(s, vmax, k, a):
    s = np.asarray(s, dtype=float)
    sa = np.power(np.maximum(s, 0.0), a)
    return vmax * sa / (sa + k**a)


def _log(s, c, d):
    s = np.asarray(s, dtype=float)
    return c * np.log1p(d * np.maximum(s, 0.0))


def response_at(curve: ChannelCurve, spend: float) -> float:
    """Predicted response for a single spend level."""
    spend = max(spend, 0.0)
    p = curve.params
    if curve.model == "hill":
        return float(_hill(spend, p["vmax"], p["k"], p["a"]))
    return float(_log(spend, p["c"], p["d"]))


def marginal_roi(curve: ChannelCurve, spend: float, value_per_response: float = 1.0) -> float:
    """Slope of the response curve at ``spend`` (revenue per incremental dollar)."""
    s = max(spend, _TINY)
    p = curve.params
    if curve.model == "hill":
        a, k, vmax = p["a"], p["k"], p["vmax"]
        sa = s**a
        denom = (sa + k**a) ** 2
        slope = vmax * a * (k**a) * (s ** (a - 1)) / denom
    else:
        slope = p["c"] * p["d"] / (1.0 + p["d"] * s)
    return float(slope * value_per_response)


def saturation_fraction(curve: ChannelCurve, spend: float) -> float:
    """Fraction of the channel's response ceiling captured at ``spend`` (in [0, 1))."""
    s = max(spend, 0.0)
    p = curve.params
    if curve.model == "hill":
        sa = s ** p["a"]
        return float(sa / (sa + p["k"] ** p["a"]))
    ds = p["d"] * s
    return float(ds / (1.0 + ds))


def _zone(curve: ChannelCurve, spend: float) -> Zone:
    f = saturation_fraction(curve, spend)
    if f < 0.33:
        return "underspend"
    if f <= 0.75:
        return "optimal"
    return "saturated"


# ---------------------------------------------------------------------------
# Fitting
# ---------------------------------------------------------------------------


def _r_squared(y: np.ndarray, y_hat: np.ndarray) -> float:
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    if ss_tot <= _TINY:
        return 0.0
    return 1.0 - ss_res / ss_tot


def _confidence(r2: float, n: int) -> Confidence:
    if r2 >= 0.8 and n >= 12:
        return "high"
    if r2 >= 0.5 and n >= MIN_POINTS:
        return "medium"
    return "low"


def fit_saturation_curve(
    obs: ChannelObservations, min_points: int = MIN_POINTS
) -> ChannelCurve | None:
    """Fit a Hill curve; fall back to log. Returns None when data is too sparse.

    None signals ``insufficient_data`` to the caller — we never fabricate a curve.
    """
    spend = np.asarray(obs.spend, dtype=float)
    response = np.asarray(obs.response, dtype=float)
    n = len(spend)
    if n < min_points or len(np.unique(spend)) < min_points:
        return None

    s_max = float(spend.max())
    r_max = float(response.max())
    if s_max <= 0 or r_max <= 0:
        return None

    hill = _try_hill(spend, response, s_max, r_max, n)
    if hill is not None and hill.r_squared >= 0.5:
        return hill

    log = _try_log(spend, response, s_max, r_max, n)
    # Prefer whichever explains more variance; fall back to hill if log fails.
    candidates = [c for c in (hill, log) if c is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda c: c.r_squared)


def _try_hill(spend, response, s_max, r_max, n) -> ChannelCurve | None:
    p0 = [r_max * 1.2, max(np.median(spend), s_max * 0.1), 1.0]
    bounds = ([_TINY, _TINY, 0.1], [r_max * 100, s_max * 100, 10.0])
    try:
        popt, _ = curve_fit(_hill, spend, response, p0=p0, bounds=bounds, maxfev=10000)
    except (RuntimeError, ValueError):
        return None
    r2 = _r_squared(response, _hill(spend, *popt))
    return ChannelCurve(
        channel="",
        model="hill",
        params={"vmax": float(popt[0]), "k": float(popt[1]), "a": float(popt[2])},
        r_squared=r2,
        n_points=n,
        confidence=_confidence(r2, n),
    )


def _try_log(spend, response, s_max, r_max, n) -> ChannelCurve | None:
    p0 = [r_max, 1.0 / max(np.median(spend), 1.0)]
    bounds = ([_TINY, _TINY], [r_max * 100, 1e6])
    try:
        popt, _ = curve_fit(_log, spend, response, p0=p0, bounds=bounds, maxfev=10000)
    except (RuntimeError, ValueError):
        return None
    r2 = _r_squared(response, _log(spend, *popt))
    return ChannelCurve(
        channel="",
        model="log",
        params={"c": float(popt[0]), "d": float(popt[1])},
        r_squared=r2,
        n_points=n,
        confidence=_confidence(r2, n),
    )


def _with_channel(curve: ChannelCurve, channel: str) -> ChannelCurve:
    return ChannelCurve(
        channel=channel,
        model=curve.model,
        params=curve.params,
        r_squared=curve.r_squared,
        n_points=curve.n_points,
        confidence=curve.confidence,
    )


def fit_channel(obs: ChannelObservations, min_points: int = MIN_POINTS) -> ChannelCurve | None:
    """Fit and stamp the channel name onto the curve."""
    curve = fit_saturation_curve(obs, min_points=min_points)
    return _with_channel(curve, obs.channel) if curve is not None else None


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------


def optimize_allocation(
    curves: list[ChannelCurve],
    current_spend: dict[str, float],
    total_budget: float,
    *,
    value_per_response: dict[str, float] | float = 1.0,
    floor_ratio: float = 0.5,
    cap_ratio: float = 2.0,
    min_mroi: float = 0.05,
    steps: int = 1000,
) -> AllocationPlan:
    """Greedy water-filling: pour each increment into the steepest curve below its cap.

    Converges to equal marginal ROI across channels — the optimum under a budget
    constraint. ``current_spend`` sets per-channel floors (floor_ratio) and caps (cap_ratio).
    """
    total_budget = max(total_budget, 0.0)
    if not curves:
        return AllocationPlan([], total_budget, 0.0, 0.0, unallocated_budget=total_budget)

    def value_of(channel: str) -> float:
        if isinstance(value_per_response, dict):
            return value_per_response.get(channel, 1.0)
        return value_per_response

    floors = {
        c.channel: max(current_spend.get(c.channel, 0.0), 0.0) * max(floor_ratio, 0.0)
        for c in curves
    }
    floor_sum = sum(floors.values())
    if floor_sum > total_budget and floor_sum > _TINY:
        scale = total_budget / floor_sum
        floors = {channel: spend * scale for channel, spend in floors.items()}

    caps = {
        c.channel: max(current_spend.get(c.channel, 0.0), 0.0) * max(cap_ratio, 0.0)
        for c in curves
    }
    # A channel with no current spend still gets headroom to be funded.
    for c in curves:
        if caps[c.channel] <= floors[c.channel]:
            caps[c.channel] = max(total_budget, floors[c.channel] + total_budget)

    alloc = {c.channel: floors[c.channel] for c in curves}
    spent = sum(alloc.values())
    step = total_budget / steps if steps > 0 and total_budget > 0 else total_budget
    remaining = total_budget - spent

    while remaining > _TINY and step > _TINY:
        increment = min(step, remaining)
        best: ChannelCurve | None = None
        best_mroi = 0.0
        for c in curves:
            if alloc[c.channel] + increment > caps[c.channel] + _TINY:
                continue
            m = marginal_roi(c, alloc[c.channel], value_of(c.channel))
            if m > best_mroi:
                best_mroi = m
                best = c
        if best is None or best_mroi < min_mroi:
            break
        alloc[best.channel] += increment
        remaining -= increment

    allocations: list[ChannelAllocation] = []
    baseline_total = 0.0
    projected_total = 0.0
    for c in curves:
        cur = current_spend.get(c.channel, 0.0)
        rec = alloc[c.channel]
        baseline = response_at(c, cur)
        projected = response_at(c, rec)
        baseline_total += baseline
        projected_total += projected
        allocations.append(
            ChannelAllocation(
                channel=c.channel,
                current_spend=cur,
                recommended_spend=rec,
                delta=rec - cur,
                projected_response=projected,
                marginal_roi=marginal_roi(c, rec, value_of(c.channel)),
                zone=_zone(c, rec),
            )
        )

    return AllocationPlan(
        allocations=allocations,
        total_budget=total_budget,
        baseline_total_response=baseline_total,
        projected_total_response=projected_total,
        unallocated_budget=max(remaining, 0.0),
    )


def insufficient_allocation(channel: str, current_spend: float) -> ChannelAllocation:
    """Hold a channel that could not be fitted at its current spend, flagged for review."""
    return ChannelAllocation(
        channel=channel,
        current_spend=current_spend,
        recommended_spend=current_spend,
        delta=0.0,
        projected_response=None,
        marginal_roi=None,
        zone="insufficient_data",
    )


def is_finite(x: float | None) -> bool:
    return x is not None and not (math.isnan(x) or math.isinf(x))


def finite_or_none(x: float | None) -> float | None:
    """Return a JSON-safe finite float or None for unavailable/non-finite values."""
    return x if is_finite(x) else None


def allocation_to_dict(allocation: ChannelAllocation) -> dict[str, float | str | None]:
    """Serialize one allocation without JSON-invalid NaN or Infinity values."""
    return {
        "channel": allocation.channel,
        "current_spend": finite_or_none(allocation.current_spend),
        "recommended_spend": finite_or_none(allocation.recommended_spend),
        "delta": finite_or_none(allocation.delta),
        "projected_response": finite_or_none(allocation.projected_response),
        "marginal_roi": finite_or_none(allocation.marginal_roi),
        "zone": allocation.zone,
    }


def allocation_plan_to_dict(plan: AllocationPlan) -> dict[str, object]:
    """Serialize an allocation plan for API responses, audit metadata, and Markdown rendering."""
    return {
        "allocations": [allocation_to_dict(item) for item in plan.allocations],
        "total_budget": finite_or_none(plan.total_budget),
        "baseline_total_response": finite_or_none(plan.baseline_total_response),
        "projected_total_response": finite_or_none(plan.projected_total_response),
        "unallocated_budget": finite_or_none(plan.unallocated_budget),
    }
