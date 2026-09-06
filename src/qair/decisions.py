"""Decision contracts and the process exit code.

One contract per measure, carrying the estimate, the threshold in force and the
resulting decision. The exit code is derived from those rows so the gate cannot
disagree with the record it was based on.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from qair.contracts import MeasurementContract
from qair.inference import INSUFFICIENT_EVIDENCE, PosteriorState
from qair.risk import RiskResult, RiskScenario

__all__ = [
    "DECISIONS",
    "build_decision_contracts",
    "build_risk_report",
    "build_posterior_state_document",
    "exit_code_from",
    "decision_for",
]

DECISIONS: dict[str, dict[str, str]] = {
    "STRONG": {
        "decision": "APPROVE",
        "reason": "credible interval above the posterior threshold",
    },
    "ADEQUATE": {
        "decision": "REVIEW",
        "reason": "credible interval straddles the posterior threshold",
    },
    "WEAK": {
        "decision": "BLOCK",
        "reason": "credible interval below the posterior threshold",
    },
    INSUFFICIENT_EVIDENCE: {
        "decision": "HOLD",
        "reason": "evidence fails its volume or freshness requirement",
    },
}

_BLOCKING = ("BLOCK", "HOLD")


def decision_for(state: PosteriorState) -> dict[str, str]:
    return dict(DECISIONS[state.band])


def build_decision_contracts(
    states: Mapping[str, PosteriorState],
    contracts: Mapping[str, MeasurementContract],
    scenario: RiskScenario,
    model_id: str,
    model_version: str,
    policy_version: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """One decision contract per measure, plus the derived gate."""
    ts = generated_at or datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    for mid, contract in contracts.items():
        st = states[mid]
        d = decision_for(st)
        lo_hi = list(st.interval) if st.reportable else None
        rows.append(
            {
                "measure_id": mid,
                "estimand": contract.estimand,
                "evidence_type": contract.evidence_type,
                "posterior_mean": round(st.mean, 4) if st.reportable else None,
                "credible_interval": (
                    [round(lo_hi[0], 4), round(lo_hi[1], 4)] if lo_hi else None
                ),
                "ci_level": st.ci_level,
                "threshold_in_force": {
                    "criterion": {
                        "operator": contract.operator,
                        "value": contract.threshold,
                    },
                    "theta_threshold": contract.theta_threshold,
                },
                "band": st.band,
                "decision": d["decision"],
                "reason": d["reason"],
                "observations": st.n_observations,
                "owner": contract.owner,
                "model_id": model_id,
                "model_version": model_version,
                "policy_version": policy_version,
                "timestamp": ts,
            }
        )
    doc: dict[str, Any] = {
        "schema_version": "1.0",
        "document": "decision_contracts",
        "generated_at": ts,
        "reporting_period": scenario.reporting_period,
        "scenario_mode": scenario.mode,
        "contracts": rows,
    }
    doc["gate"] = _gate(rows)
    return doc


def _gate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    blocking = [r["measure_id"] for r in rows if r["decision"] in _BLOCKING]
    review = [r["measure_id"] for r in rows if r["decision"] == "REVIEW"]
    return {
        "pass": not blocking,
        "blocking": blocking,
        "review": review,
        "exit_code": 0 if not blocking else 1,
        "derivation": "exit_code is 1 if any contract carries BLOCK or HOLD, else 0",
    }


def exit_code_from(decision_contracts: Mapping[str, Any]) -> int:
    """The process exit code, read off the emitted contracts."""
    return int(decision_contracts["gate"]["exit_code"])


def build_posterior_state_document(
    states: Mapping[str, PosteriorState],
    model_id: str,
    model_version: str,
    n_records: int,
    reported_at: str,
    sensitivity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The posterior_state.json document: one entry per measure."""
    doc: dict[str, Any] = {
        "schema_version": "1.0",
        "document": "posterior_state",
        "model_id": model_id,
        "model_version": model_version,
        "n_records": n_records,
        "reported_at": reported_at,
        "measures": {mid: st.to_dict() for mid, st in states.items()},
    }
    if sensitivity is not None:
        doc["prior_sensitivity"] = dict(sensitivity)
    return doc


def build_risk_report(
    result: RiskResult,
    scenario: RiskScenario,
    attribution: Mapping[str, Any],
    stability: Mapping[str, Any],
    scenario_results: Mapping[str, Mapping[str, float]],
    generated_at: str | None = None,
) -> dict[str, Any]:
    """The risk_report.json document: the simulation and its assumptions."""
    ts = generated_at or datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": "1.0",
        "document": "risk_report",
        "generated_at": ts,
        "reporting_period": scenario.reporting_period,
        "currency": scenario.currency,
        "assumptions": {
            "mode": scenario.mode,
            "monthly_decisions": scenario.monthly_decisions,
            "control_instances_per_month": scenario.control_instances_per_month,
            "escalation_probability": scenario.escalation_probability,
            "consequence": scenario.consequence,
            "dependence_source": scenario.dependence_source,
            "dependence_order": list(scenario.dependence_order),
            "dependence_matrix": scenario.dependence_matrix.tolist(),
            "healthy_state": list(scenario.healthy_state),
        },
        "simulation": {
            "n_simulations": result.n_simulations,
            "primary_seed": result.seed,
            "var_level": result.var_level,
            "measures_included": list(result.measures),
            "measures_excluded": list(result.excluded_measures),
        },
        "results": {
            "expected_loss": round(result.expected_loss),
            "median_loss": round(result.median_loss),
            "var": round(result.var),
            "tce": round(result.tce),
            "zero_loss_share": round(result.zero_loss_share, 4),
            "expected_by_measure": {
                k: round(v) for k, v in result.expected_by_measure().items()
            },
        },
        "tail_attribution": attribution,
        "seed_stability": stability,
        "counterfactual_scenarios": {k: dict(v) for k, v in scenario_results.items()},
        "interpretation_floor": (
            "Do not interpret a difference smaller than the seed spread in "
            "seed_stability."
        ),
    }
