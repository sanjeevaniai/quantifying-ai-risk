"""The pipeline reproduces its documented reference values.

These come from running the pipeline on tests/fixtures/telemetry.jsonl. They are
here to catch an unintended change in the model, not to certify a result.

The posterior values are deterministic. The monetary values are simulated, so
they carry tolerances derived from the seed-to-seed spread that
`test_seed_spread_is_within_the_documented_range` asserts.
"""

from __future__ import annotations

import pytest

REFERENCE = {
    "expected_loss": 2_402_894,
    "var": 6_916_408,
    "tce": 14_108_629,
    "zero_loss_share": 0.100,
    "fairness_expected_loss": 592_740,
    "fairness_tail_share": 0.575,
    "hold_fairness_healthy_tce_change": -0.422,
}

# Expected loss and VaR move ~3% and ~1% across seeds; the TCE moves ~11%.
TOLERANCE = {"expected_loss": 0.10, "var": 0.10, "tce": 0.20,
             "fairness_expected_loss": 0.20}
SHARE_TOLERANCE = 0.05


def close(actual, expected, relative):
    return abs(actual - expected) <= relative * expected


# --- deterministic ---------------------------------------------------------

def test_fairness_posterior(states):
    st = states["fairness_parity_75"]
    assert st.n_observations == 13
    assert (st.n_passed, st.n_failed) == (4, 9)
    assert (st.alpha, st.beta) == (6.0, 17.0)
    assert round(st.mean, 4) == 0.2609


def test_observation_counts(states):
    counts = {m: st.n_observations for m, st in states.items()}
    assert counts == {
        "performance_per_decision": 1000,
        "data_quality_50": 20,
        "drift_distance_50": 20,
        "fairness_parity_75": 13,
        "security_authz_50": 20,
        "control_execution": 8,
    }


def test_bands(states):
    assert {m: st.band for m, st in states.items()} == {
        "performance_per_decision": "STRONG",
        "data_quality_50": "WEAK",
        "drift_distance_50": "WEAK",
        "fairness_parity_75": "WEAK",
        "security_authz_50": "ADEQUATE",
        "control_execution": "WEAK",
    }


def test_confidence_rises_after_the_drift_injection(records):
    """The model is more confident on inputs it represents less well, which is why
    confidence alone is not a monitoring signal."""
    import numpy as np

    before = np.mean([r["confidence"] for r in records[:600]])
    after = np.mean([r["confidence"] for r in records[600:]])
    assert after > before


# --- simulated -------------------------------------------------------------

def test_seed_spread_is_within_the_documented_range(stability):
    """Every monetary tolerance below is only defensible while this holds."""
    spread = stability["tce"]["relative_spread"]
    assert 0.04 < spread < 0.20, f"TCE seed spread is {spread:.1%}"
    assert spread < TOLERANCE["tce"]
    assert stability["expected_loss"]["relative_spread"] < TOLERANCE["expected_loss"]
    assert stability["var"]["relative_spread"] < TOLERANCE["var"]


@pytest.mark.parametrize("key, getter", [
    ("expected_loss", lambda b: b.expected_loss),
    ("var", lambda b: b.var),
    ("tce", lambda b: b.tce),
])
def test_headline_statistics(baseline, key, getter):
    assert close(getter(baseline), REFERENCE[key], TOLERANCE[key])


def test_zero_loss_share(baseline):
    assert abs(baseline.zero_loss_share - REFERENCE["zero_loss_share"]) <= SHARE_TOLERANCE


def test_fairness_expected_loss(baseline):
    assert close(baseline.expected_by_measure()["fairness_parity_75"],
                 REFERENCE["fairness_expected_loss"],
                 TOLERANCE["fairness_expected_loss"])


def test_fairness_dominates_the_tail(baseline):
    shares = baseline.tail_shares()
    assert max(shares, key=shares.get) == "fairness_parity_75"
    assert abs(shares["fairness_parity_75"] - REFERENCE["fairness_tail_share"]) <= SHARE_TOLERANCE


def test_the_tail_leader_is_not_the_expected_loss_leader(baseline):
    """Ranking by mean cost and by tail contribution give different answers."""
    top_tail = max(baseline.tail_shares().items(), key=lambda kv: kv[1])[0]
    top_mean = max(baseline.expected_by_measure().items(), key=lambda kv: kv[1])[0]
    assert top_tail != top_mean


def test_holding_fairness_healthy_moves_the_tail_most(attribution):
    changes = {m: v["tce_change"] for m, v in attribution["hold_healthy"].items()}
    assert min(changes, key=changes.get) == "fairness_parity_75"
    assert abs(changes["fairness_parity_75"]
               - REFERENCE["hold_fairness_healthy_tce_change"]) <= 0.10


# --- counterfactual scenarios ----------------------------------------------

def test_monitoring_gap_matches_baseline(scenario_runs):
    """Stale evidence cannot move a posterior, so this row is identical by
    construction. The sufficiency check is what catches it."""
    base, gap = scenario_runs["baseline"], scenario_runs["monitoring_gap"]
    assert (gap.expected_loss, gap.var, gap.tce) == (base.expected_loss, base.var, base.tce)


def test_missing_documentation_excludes_the_measure_and_the_loss_falls(scenario_runs):
    """The reported loss falls because a measure stopped being measurable."""
    run, base = scenario_runs["missing_documentation"], scenario_runs["baseline"]
    assert "control_execution" in run.excluded_measures
    assert run.expected_loss < base.expected_loss


def test_added_failing_windows_raise_the_tail(scenario_runs):
    base = scenario_runs["baseline"].tce
    assert scenario_runs["fairness_degradation"].tce > base
    assert scenario_runs["drift_spike"].tce > base
