"""Evidence typing, the control register, and missing timestamps."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from qair.contracts import ContractError
from qair.evidence import (
    CONTROL_STATES,
    ControlRecord,
    ControlRegister,
    Observation,
    check_evidence_type,
    divergences,
)
from qair.inference import estimate

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)


def _obs(measure_id, evidence_type, passed=True):
    return Observation(measure_id=measure_id, evidence_type=evidence_type,
                       passed=passed, observed_at=NOW)


def test_control_evidence_cannot_update_a_behavioural_measure(contracts):
    with pytest.raises(ContractError, match="cannot update"):
        check_evidence_type(
            contracts["fairness_parity_75"], _obs("fairness_parity_75", "control")
        )


def test_the_refusal_fires_in_both_directions(contracts):
    with pytest.raises(ContractError, match="cannot update"):
        check_evidence_type(
            contracts["control_execution"], _obs("control_execution", "system_behavior")
        )


def test_type_matched_control_evidence_is_allowed(contracts):
    """control_execution is a measure whose evidence is the control register."""
    check_evidence_type(contracts["control_execution"], _obs("control_execution", "control"))


def test_estimate_refuses_before_any_arithmetic(contracts):
    with pytest.raises(ContractError):
        estimate(contracts["fairness_parity_75"],
                 [_obs("fairness_parity_75", "control")], NOW)


def test_the_register_refuses_to_produce_behavioural_observations(register, contracts):
    with pytest.raises(ContractError, match="cannot produce"):
        register.observations(contracts["fairness_parity_75"])


def test_control_state_document_carries_no_estimate(register, states):
    """The register records states. The posterior lives in posterior_state.json."""
    doc = register.to_document(divergences(register, states), reported_at=NOW.isoformat())
    text = str(doc)
    for banned in ("alpha", "beta", "credible_interval", "posterior"):
        assert banned not in text, f"control_state carries {banned!r}"
    for row in doc["controls"]:
        assert set(row) == {"control_id", "description", "owner", "state",
                            "last_evidence", "covers_measure"}
    assert "band" not in doc
    assert "mean" not in doc


def test_control_execution_has_a_posterior_and_a_band(states):
    st = states["control_execution"]
    assert st.alpha > 0 and st.beta > 0
    assert st.band in ("STRONG", "ADEQUATE", "WEAK")
    assert st.estimand.startswith("theta =")


def test_evidenced_is_the_only_passing_state():
    for state in CONTROL_STATES:
        r = ControlRecord("c", "d", "o", state, "2026-09-01")
        assert r.evidenced == (state == "EVIDENCED")


def test_attested_only_and_stale_both_fail_the_criterion(register):
    """The criterion is EVIDENCED. Attested-but-unverified and out-of-date both
    fail it."""
    by_state = {r.control_id: r for r in register.records}
    assert not by_state["quarterly_fairness_review"].evidenced
    assert not by_state["incident_runbook_exercised"].evidenced


def test_divergence_produces_two_findings_with_two_owners(register, states):
    found = divergences(register, states)
    assert found
    d = next(x for x in found if x["measure_id"] == "fairness_parity_75")
    assert d["control_state"] == "ATTESTED_ONLY"
    assert d["measured_band"] == "WEAK"
    assert len(d["findings"]) == 2
    owners = {f["owner"] for f in d["findings"]}
    assert len(owners) == 2, "two findings, two owners"


def test_ageing_the_register_moves_every_dated_record(register):
    aged = register.aged(120)
    for before, after in zip(register.records, aged.records):
        if before.last_evidence is None:
            assert after.last_evidence is None
        else:
            assert after.last_evidence < before.last_evidence
        assert after.state == before.state


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------

def test_a_control_without_an_evidence_date_gets_no_timestamp(contracts):
    """No fallback timestamp is manufactured for missing evidence."""
    register = ControlRegister(
        records=[ControlRecord("c1", "d", "o", "NO_EVIDENCE", None)],
        register_refreshed_at="2026-09-08T00:00:00+00:00",
    )
    obs = register.observations(contracts["control_execution"])
    assert obs[0].observed_at is None
    assert obs[0].passed is False


def test_missing_dates_make_a_measure_insufficient_not_fresh(contracts, reported_at):
    """If nothing carries a date, freshness cannot be established."""
    from qair.inference import INSUFFICIENT_EVIDENCE, estimate

    contract = contracts["control_execution"]
    register = ControlRegister(
        records=[ControlRecord(f"c{i}", "d", "o", "EVIDENCED", None) for i in range(8)]
    )
    st = estimate(contract, register.observations(contract), reported_at)
    assert st.band == INSUFFICIENT_EVIDENCE
    assert "freshness" in st.sufficiency.reason


def test_offset_aware_timestamps_are_converted_not_relabelled():
    """An offset-aware timestamp keeps the instant it refers to."""
    from datetime import datetime, timedelta, timezone

    from qair.timeutil import to_utc

    aware = datetime(2026, 9, 11, 12, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    converted = to_utc(aware)
    assert converted.tzinfo == timezone.utc
    assert converted.hour == 6 and converted.minute == 30
    assert converted == aware


def test_naive_timestamps_are_assumed_utc():
    from datetime import datetime, timezone

    from qair.timeutil import to_utc

    naive = datetime(2026, 9, 11, 12, 0)
    assert to_utc(naive) == datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
