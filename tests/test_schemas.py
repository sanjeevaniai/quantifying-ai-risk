"""Generated documents validate against the schemas in schemas/."""

from __future__ import annotations

import json

import jsonschema
import pytest

from qair.decisions import (
    build_decision_contracts,
    build_posterior_state_document,
    build_risk_report,
)
from qair.evidence import divergences
from qair.validation import load_schema, validate_document


def test_every_schema_is_a_valid_draft_2020_12_schema(root):
    files = sorted((root / "schemas").glob("*.schema.json"))
    assert files
    for path in files:
        jsonschema.Draft202012Validator.check_schema(json.loads(path.read_text()))


def test_every_telemetry_record_validates(records):
    for r in records:
        validate_document(r, "telemetry_event")


def test_a_record_missing_a_required_field_is_rejected(records):
    broken = dict(records[0])
    del broken["group"]
    with pytest.raises(jsonschema.ValidationError):
        validate_document(broken, "telemetry_event")


def test_date_time_format_is_actually_checked(records):
    """Formats are declared, so they must be enforced rather than annotated."""
    broken = dict(records[0], captured_at="the fourteenth of March")
    with pytest.raises(jsonschema.ValidationError, match="date-time"):
        validate_document(broken, "telemetry_event")


def test_every_shipped_contract_validates(root):
    for path in sorted((root / "contracts").glob("*.json")):
        validate_document(json.loads(path.read_text()), "measurement_contract")


def test_posterior_state_validates(states, scenario):
    doc = build_posterior_state_document(states, "credit_decisioning", "3.2", 1000,
                                         scenario.reported_at)
    validate_document(doc, "posterior_state")


def test_control_state_validates(register, states, scenario):
    doc = register.to_document(divergences(register, states),
                               reported_at=scenario.reported_at)
    validate_document(doc, "control_state")


def test_decision_contracts_validate(states, contracts, scenario, records):
    doc = build_decision_contracts(
        states, contracts, scenario, records[0]["model_id"],
        records[0]["model_version"], records[0]["policy_version"],
        generated_at=scenario.reported_at,
    )
    validate_document(doc, "decision_contract")


def test_risk_report_validates(baseline, scenario, attribution, stability, scenario_runs):
    results = {
        name: {"expected_loss": round(r.expected_loss), "var": round(r.var),
               "tce": round(r.tce), "excluded": list(r.excluded_measures)}
        for name, r in scenario_runs.items()
    }
    doc = build_risk_report(baseline, scenario, attribution, stability, results,
                            generated_at=scenario.reported_at)
    validate_document(doc, "risk_report")


def test_schemas_accept_any_number_of_measures(states, scenario):
    """The schema constrains the shape of a measure entry, not how many there are."""
    doc = build_posterior_state_document(states, "m", "1", 10, scenario.reported_at)
    entry = doc["measures"]["fairness_parity_75"]
    doc["measures"]["another_measure"] = dict(entry, measure_id="another_measure")
    validate_document(doc, "posterior_state")


def test_schemas_reject_a_malformed_measure_id(states, scenario):
    doc = build_posterior_state_document(states, "m", "1", 10, scenario.reported_at)
    entry = doc["measures"]["fairness_parity_75"]
    doc["measures"]["Not A Measure Id"] = dict(entry, measure_id="Not A Measure Id")
    with pytest.raises(jsonschema.ValidationError):
        validate_document(doc, "posterior_state")


def test_risk_report_rejects_an_unknown_mode(baseline, scenario, attribution, stability):
    doc = build_risk_report(baseline, scenario, attribution, stability, {},
                            generated_at=scenario.reported_at)
    doc["assumptions"]["mode"] = "validated"
    with pytest.raises(jsonschema.ValidationError):
        validate_document(doc, "risk_report")


def test_posterior_state_uses_a_shared_measure_definition():
    """One definition reused, not one copy per measure."""
    schema = load_schema("posterior_state")
    assert "measure_state" in schema["$defs"]
    assert schema["properties"]["measures"]["additionalProperties"]["$ref"] == \
        "#/$defs/measure_state"
