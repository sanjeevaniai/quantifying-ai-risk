"""Measurement functions for the worked credit-decisioning example.

`qair` knows nothing about this system. This module turns its decision stream
into typed observations, using the window length, criterion and parameters
declared in each contract. Replace it to point the engine at your own system.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

import numpy as np

from qair.contracts import MeasurementContract
from qair.evidence import Observation
from qair.timeutil import parse_utc

__all__ = [
    "MEASURE_FUNCTIONS",
    "caller_volume_share",
    "data_quality_50",
    "drift_distance",
    "drift_distance_50",
    "fairness_parity_75",
    "parity_ratio",
    "performance_per_decision",
    "security_authz_50",
    "window_observations",
]


def _compare(value: float, operator: str, threshold: float) -> bool:
    if operator == ">=":
        return value >= threshold
    if operator == "<=":
        return value <= threshold
    if operator == "==":
        return value == threshold
    raise ValueError(f"unsupported operator {operator!r}")


def _windows(records: Sequence[dict[str, Any]], length: int):
    """Non-overlapping windows. A partial trailing window is not an observation."""
    for start in range(0, len(records) - length + 1, length):
        yield start // length, records[start : start + length]


def _observation(contract, index, statistic, at, detail=""):
    return Observation(
        measure_id=contract.measure_id,
        evidence_type=contract.evidence_type,
        passed=_compare(statistic, contract.operator, contract.threshold),
        observed_at=at,
        statistic=statistic,
        window_index=index,
        detail=detail,
    )


def drift_distance(X_window, ref_means, ref_stds, scale: float) -> float:
    """Mean normalised shift from the training reference, divided by ``scale``."""
    return float(np.mean(np.abs(X_window.mean(axis=0) - ref_means) / ref_stds)) / scale


def parity_ratio(records, reference_group="A", groups=("A", "B", "C", "D"), smoothing=1):
    """Worst group approval rate divided by the reference group's rate.

    Rates are Laplace-smoothed: a 75-decision window can leave a group with very
    few decisions, and an unsmoothed ratio then swings on a single outcome.
    """
    approved = np.array([r["decision"] == "APPROVED" for r in records])
    seen = np.array([r["group"] for r in records])
    rates = {
        g: (approved[seen == g].sum() + smoothing) / ((seen == g).sum() + 2 * smoothing)
        for g in groups
    }
    ref = rates[reference_group]
    others = [g for g in groups if g != reference_group]
    return float(min(rates[g] / ref for g in others))


def performance_per_decision(records, contract, **_):
    """One decision per window. Correctness is excluded: labels arrive later."""
    min_conf = contract.param("min_confidence")
    max_latency = contract.param("max_latency_ms")
    out = []
    for i, w in _windows(records, contract.window_length):
        r = w[0]
        ok = r["confidence"] >= min_conf and r["latency_ms"] <= max_latency and not r["error"]
        out.append(_observation(contract, i, 1.0 if ok else 0.0, parse_utc(r["captured_at"])))
    return out


def data_quality_50(records, contract, **_):
    """Share of records in the window passing all three input checks."""
    out = []
    for i, w in _windows(records, contract.window_length):
        share = float(np.mean([
            r["dq_null_ct"] == 0 and r["dq_range_viol"] == 0 and r["dq_schema_ok"] for r in w
        ]))
        out.append(_observation(contract, i, share, parse_utc(w[-1]["captured_at"])))
    return out


def drift_distance_50(records, contract, ref_means=None, ref_stds=None, **_):
    """Distance from the training reference, per window."""
    if ref_means is None or ref_stds is None:
        raise ValueError("drift_distance_50 needs the training reference distribution")
    scale = contract.param("scale")
    out = []
    for i, w in _windows(records, contract.window_length):
        X = np.array([r["input_features"] for r in w])
        d = drift_distance(X, ref_means, ref_stds, scale)
        out.append(_observation(contract, i, d, parse_utc(w[-1]["captured_at"])))
    return out


def fairness_parity_75(records, contract, **_):
    """Parity ratio per window, against the criterion in the contract."""
    ref = contract.param("reference_group")
    groups = tuple(contract.param("groups"))
    smoothing = contract.param("smoothing")
    out = []
    for i, w in _windows(records, contract.window_length):
        stat = parity_ratio(w, ref, groups, smoothing)
        out.append(_observation(contract, i, stat, parse_utc(w[-1]["captured_at"])))
    return out


def security_authz_50(records, contract, **_):
    """Share of calls that authenticated and broke no policy rule.

    Caller volume is not part of the criterion; it is derived, not recorded. See
    `caller_volume_share`.
    """
    out = []
    for i, w in _windows(records, contract.window_length):
        share = float(np.mean([r["auth_result"] and not r["policy_violation"] for r in w]))
        out.append(_observation(contract, i, share, parse_utc(w[-1]["captured_at"])))
    return out


def caller_volume_share(records, window: int = 50) -> list[dict[str, Any]]:
    """Per-window share of calls by caller. Derived from caller_id, not recorded."""
    out = []
    for i, w in _windows(records, window):
        counts: dict[str, int] = {}
        for r in w:
            counts[r["caller_id"]] = counts.get(r["caller_id"], 0) + 1
        out.append({"window_index": i,
                    "shares": {k: round(v / len(w), 3) for k, v in sorted(counts.items())}})
    return out


MEASURE_FUNCTIONS: dict[str, Callable[..., list[Observation]]] = {
    "performance_per_decision": performance_per_decision,
    "data_quality_50": data_quality_50,
    "drift_distance_50": drift_distance_50,
    "fairness_parity_75": fairness_parity_75,
    "security_authz_50": security_authz_50,
}


def window_observations(contract: MeasurementContract, records, **context):
    """Dispatch to the measurement function for a behavioural measure.

    `control_execution` is not derived from the decision stream. It uses the
    separate control register loaded in Notebook 2.
    """
    fn = MEASURE_FUNCTIONS.get(contract.measure_id)
    if fn is None:
        raise KeyError(
            f"No measurement function for {contract.measure_id!r} in measures.py. "
            f"Registered: {sorted(MEASURE_FUNCTIONS)}"
        )
    return fn(records, contract, **context)
