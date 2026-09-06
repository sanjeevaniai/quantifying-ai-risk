"""Contract loading and validation."""

from __future__ import annotations

import json

import pytest

from qair.contracts import ContractError, load_contract, load_contracts


def test_loads_every_contract_in_the_directory(contracts):
    assert set(contracts) == {p.stem for p in (
        __import__("pathlib").Path(__file__).resolve().parents[1] / "contracts"
    ).glob("*.json")}


def test_engine_does_not_require_a_fixed_number_of_measures(tmp_path, root):
    """A contracts directory with any number of measures loads."""
    source = json.loads((root / "contracts" / "data_quality_50.json").read_text())
    for i in range(3):
        c = dict(source, measure_id=f"extra_measure_{i}")
        (tmp_path / f"extra_measure_{i}.json").write_text(json.dumps(c))
    loaded = load_contracts(tmp_path)
    assert len(loaded) == 3
    assert set(loaded) == {f"extra_measure_{i}" for i in range(3)}


def test_measure_id_must_match_the_filename(tmp_path, root):
    source = json.loads((root / "contracts" / "data_quality_50.json").read_text())
    (tmp_path / "wrong_name.json").write_text(json.dumps(source))
    with pytest.raises(ContractError, match="does not match the filename"):
        load_contracts(tmp_path)


def test_every_contract_states_an_estimand(contracts):
    for mid, c in contracts.items():
        assert c.estimand.strip(), mid


def test_window_length_comes_from_the_contract(contracts):
    assert contracts["fairness_parity_75"].window_length == 75
    assert contracts["fairness_parity_75"].window == "75 decisions"
    assert contracts["performance_per_decision"].window == "1 decision"


def test_fairness_contract_values(contracts):
    c = contracts["fairness_parity_75"]
    assert c.evidence_type == "system_behavior"
    assert list(c.observable_fields) == ["decision", "group"]
    assert c.operator == ">=" and c.threshold == 0.80
    assert c.theta_threshold == 0.90
    assert c.param("reference_group") == "A"


def test_measurement_parameters_live_in_the_contract(contracts):
    """The measurement function reads its constants from the contract, so the
    contract is the only place they are written down."""
    c = contracts["performance_per_decision"]
    assert c.param("min_confidence") == 0.70
    assert c.param("max_latency_ms") == 300
    assert contracts["drift_distance_50"].param("scale") == 1.5


def test_unknown_parameter_raises(contracts):
    with pytest.raises(ContractError, match="no parameter"):
        contracts["data_quality_50"].param("not_declared")


def test_only_control_execution_uses_control_evidence(contracts):
    assert [m for m, c in contracts.items() if c.evidence_type == "control"] == \
        ["control_execution"]


def test_missing_contract_raises(tmp_path):
    with pytest.raises(ContractError, match="No contract"):
        load_contract("not_a_measure", tmp_path)


def test_contract_missing_a_field_raises(tmp_path, root):
    raw = json.loads((root / "contracts" / "fairness_parity_75.json").read_text())
    del raw["estimand"]
    (tmp_path / "fairness_parity_75.json").write_text(json.dumps(raw))
    with pytest.raises(ContractError, match="missing field"):
        load_contract("fairness_parity_75", tmp_path)


def test_exposure_derives_from_window_length(contracts, scenario):
    c = contracts["fairness_parity_75"]
    assert scenario.exposure_windows(c) == scenario.monthly_decisions // 75
    assert scenario.exposure_windows(contracts["control_execution"]) == \
        scenario.control_instances_per_month


def test_scenario_must_cover_every_loaded_measure(scenario, contracts):
    scenario.check_covers(contracts)
    incomplete = dict(contracts)
    incomplete["unknown_measure"] = contracts["data_quality_50"]
    with pytest.raises(ContractError, match="does not match contracts"):
        scenario.check_covers(incomplete)


def test_the_shipped_example_registers_one_function_per_behavioural_measure(contracts):
    """measures.MEASURE_FUNCTIONS matches the shipped contracts.

    Also catches a measurement function left registered by another test module.
    """
    import measures

    behavioural = {m for m, c in contracts.items() if c.evidence_type != "control"}
    assert set(measures.MEASURE_FUNCTIONS) == behavioural
