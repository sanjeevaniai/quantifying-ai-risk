"""Adding a measure needs a contract, a measurement function and a scenario entry.

No engine change. This test does exactly what `exercises.md` asks a reader to do,
then runs estimation, simulation and both document schemas over seven measures.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

import measures
from qair.contracts import load_contracts
from qair.decisions import build_decision_contracts, build_posterior_state_document, exit_code_from
from qair.inference import estimate
from qair.risk import load_scenario, simulate
from qair.validation import validate_document

NEW_MEASURE = "latency_tail_50"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def measurement_function():
    """Register the new measurement function, and unregister it afterwards."""
    sys.path.insert(0, str(FIXTURES))
    try:
        from extra_measures import latency_tail_50
    finally:
        sys.path.remove(str(FIXTURES))
    measures.MEASURE_FUNCTIONS[NEW_MEASURE] = latency_tail_50
    yield latency_tail_50
    del measures.MEASURE_FUNCTIONS[NEW_MEASURE]


@pytest.fixture(scope="module")
def seven(root, tmp_path_factory, measurement_function):
    """A contracts directory and scenario file carrying one extra measure."""
    tmp = tmp_path_factory.mktemp("seven")
    shutil.copytree(root / "contracts", tmp / "contracts")
    shutil.copy(FIXTURES / "contracts" / f"{NEW_MEASURE}.json", tmp / "contracts")

    raw = yaml.safe_load((root / "risk_scenario.yaml").read_text())
    raw["dependence"]["order"].append(NEW_MEASURE)
    matrix = np.array(raw["dependence"]["matrix"], dtype=float)
    matrix = np.pad(matrix, ((0, 1), (0, 1)))
    matrix[-1, -1] = 1.0
    # Correlated with performance, since both are driven by serving latency.
    i = raw["dependence"]["order"].index("performance_per_decision")
    matrix[i, -1] = matrix[-1, i] = 0.5
    raw["dependence"]["matrix"] = matrix.tolist()
    raw["escalation_probability"][NEW_MEASURE] = 0.0004
    raw["consequence"][NEW_MEASURE] = {"median": 150000, "sigma": 0.9}
    (tmp / "risk_scenario.yaml").write_text(yaml.safe_dump(raw))

    contracts = load_contracts(tmp / "contracts")
    scenario = load_scenario(tmp / "risk_scenario.yaml")
    scenario.check_covers(contracts)
    return contracts, scenario


@pytest.fixture(scope="module")
def seven_states(seven, records, register, reference, reported_at):
    contracts, _ = seven
    ref_means, ref_stds = reference
    return {
        mid: estimate(
            c,
            (register.observations(c) if c.evidence_type == "control"
             else measures.window_observations(c, records,
                                               ref_means=ref_means, ref_stds=ref_stds)),
            reported_at,
        )
        for mid, c in contracts.items()
    }


def test_the_contract_validates_against_the_schema():
    raw = json.loads((FIXTURES / "contracts" / f"{NEW_MEASURE}.json").read_text())
    validate_document(raw, "measurement_contract")


def test_the_new_measure_loads_alongside_the_others(seven, contracts):
    seven_contracts, _ = seven
    assert len(seven_contracts) == len(contracts) + 1
    assert NEW_MEASURE in seven_contracts
    assert seven_contracts[NEW_MEASURE].param("max_latency_ms") == 260


def test_a_scenario_missing_the_new_measure_is_rejected(seven, scenario):
    """The shipped scenario does not know about it, and says so."""
    from qair.contracts import ContractError

    seven_contracts, _ = seven
    with pytest.raises(ContractError, match=NEW_MEASURE):
        scenario.check_covers(seven_contracts)


def test_estimation_produces_a_posterior_for_it(seven_states, contracts):
    assert len(seven_states) == len(contracts) + 1
    st = seven_states[NEW_MEASURE]
    assert st.n_observations == 20
    assert st.n_passed + st.n_failed == st.n_observations
    assert st.band in ("STRONG", "ADEQUATE", "WEAK")
    assert 0.0 < st.mean < 1.0


def test_the_existing_measures_are_unchanged(seven_states, states):
    """Adding a measure must not move the others."""
    for mid, st in states.items():
        added = seven_states[mid]
        assert (added.alpha, added.beta) == (st.alpha, st.beta)
        assert added.band == st.band


def test_simulation_includes_it(seven, seven_states):
    contracts, scenario = seven
    run = simulate(seven_states, contracts, scenario, n=8000, seed=42)
    assert NEW_MEASURE in run.measures
    assert run.per_measure_losses.shape[1] == len(run.measures)
    assert NEW_MEASURE in run.expected_by_measure()
    assert run.expected_loss > 0


def test_posterior_state_validates_with_seven_measures(seven, seven_states):
    _, scenario = seven
    doc = build_posterior_state_document(seven_states, "credit_decisioning", "3.2",
                                         1000, scenario.reported_at)
    validate_document(doc, "posterior_state")
    assert NEW_MEASURE in doc["measures"]


def test_decision_contracts_validate_with_seven_measures(seven, seven_states):
    contracts, scenario = seven
    doc = build_decision_contracts(seven_states, contracts, scenario,
                                   "credit_decisioning", "3.2", "credit_policy_2026_04",
                                   generated_at=scenario.reported_at)
    validate_document(doc, "decision_contract")
    assert len(doc["contracts"]) == len(contracts)
    assert any(r["measure_id"] == NEW_MEASURE for r in doc["contracts"])
    assert exit_code_from(doc) in (0, 1)

