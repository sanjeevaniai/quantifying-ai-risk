"""Decision contracts and the derived exit code."""

from __future__ import annotations

import pytest

from qair.decisions import (
    DECISIONS,
    build_decision_contracts,
    build_posterior_state_document,
    build_risk_report,
    exit_code_from,
)
from qair.inference import INSUFFICIENT_EVIDENCE


@pytest.fixture(scope="module")
def decision_contracts(states, contracts, scenario, records):
    return build_decision_contracts(
        states, contracts, scenario,
        model_id=records[0]["model_id"],
        model_version=records[0]["model_version"],
        policy_version=records[0]["policy_version"],
        generated_at=scenario.reported_at,
    )


def test_one_contract_per_measure(decision_contracts, contracts):
    assert len(decision_contracts["contracts"]) == len(contracts)


def test_each_contract_carries_the_fields_a_pipeline_needs(decision_contracts):
    required = {
        "measure_id", "posterior_mean", "credible_interval", "threshold_in_force",
        "decision", "reason", "model_id", "model_version", "policy_version",
        "timestamp",
    }
    for row in decision_contracts["contracts"]:
        assert required <= set(row), f"{row['measure_id']} is missing {required - set(row)}"


def test_exit_code_is_derived_from_the_rows(decision_contracts):
    rows = decision_contracts["contracts"]
    blocking = [r["measure_id"] for r in rows if r["decision"] in ("BLOCK", "HOLD")]
    assert decision_contracts["gate"]["blocking"] == blocking
    assert decision_contracts["gate"]["exit_code"] == (1 if blocking else 0)
    assert exit_code_from(decision_contracts) == decision_contracts["gate"]["exit_code"]


def test_the_gate_agrees_with_the_rows(decision_contracts):
    rows = decision_contracts["contracts"]
    all_approve = all(r["decision"] == "APPROVE" for r in rows)
    assert decision_contracts["gate"]["pass"] is (
        not [r for r in rows if r["decision"] in ("BLOCK", "HOLD")]
    )
    if all_approve:
        assert exit_code_from(decision_contracts) == 0


def test_band_maps_to_decision(): 
    assert set(DECISIONS) == {"STRONG", "ADEQUATE", "WEAK", INSUFFICIENT_EVIDENCE}
    assert DECISIONS["STRONG"]["decision"] == "APPROVE"
    assert DECISIONS["ADEQUATE"]["decision"] == "REVIEW"
    assert DECISIONS["WEAK"]["decision"] == "BLOCK"
    assert DECISIONS[INSUFFICIENT_EVIDENCE]["decision"] == "HOLD"


def test_insufficient_evidence_holds_rather_than_passing(
    states, contracts, scenario, records, register, reported_at
):
    """A measure that cannot be reported must not silently pass a gate."""
    from qair.risk import apply_counterfactual

    modified = apply_counterfactual("missing_documentation", states, scenario,
                                    contracts=contracts, control_register=register,
                                    reported_at=reported_at)
    doc = build_decision_contracts(
        modified, contracts, scenario, records[0]["model_id"],
        records[0]["model_version"], records[0]["policy_version"],
        generated_at=scenario.reported_at,
    )
    row = next(r for r in doc["contracts"] if r["measure_id"] == "control_execution")
    assert row["band"] == INSUFFICIENT_EVIDENCE
    assert row["decision"] == "HOLD"
    assert row["posterior_mean"] is None
    assert row["credible_interval"] is None
    assert "control_execution" in doc["gate"]["blocking"]
    assert exit_code_from(doc) == 1


def test_threshold_in_force_comes_from_the_contract(decision_contracts, contracts):
    for row in decision_contracts["contracts"]:
        c = contracts[row["measure_id"]]
        assert row["threshold_in_force"]["criterion"]["value"] == c.threshold
        assert row["threshold_in_force"]["criterion"]["operator"] == c.operator
        assert row["threshold_in_force"]["theta_threshold"] == c.theta_threshold
        assert row["owner"] == c.owner


def test_risk_report_carries_its_assumptions(baseline, scenario, attribution, stability):
    doc = build_risk_report(baseline, scenario, attribution, stability, {},
                            generated_at=scenario.reported_at)
    assert doc["assumptions"]["mode"] == "illustrative"
    assert doc["assumptions"]["dependence_source"] == "declared"
    assert doc["assumptions"]["escalation_probability"]
    assert doc["assumptions"]["consequence"]
    assert "seed spread" in doc["interpretation_floor"]


def test_posterior_state_document_carries_the_reporting_fields(states, scenario):
    doc = build_posterior_state_document(states, "m", "1", 1000, scenario.reported_at)
    for entry in doc["measures"].values():
        assert entry["estimand"]
        assert entry["prior"]["mode"] == "illustrative"
        assert entry["band"]
        assert "sufficiency" in entry
