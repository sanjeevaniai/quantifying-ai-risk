"""Estimation invariants: the update, the bands, and sufficiency."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from qair.inference import (
    INSUFFICIENT_EVIDENCE,
    band_for,
    credible_interval,
    estimate,
    prior_sensitivity,
    update,
)
from qair.evidence import Observation

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)


def test_one_window_is_one_observation():
    a, b = 2.0, 8.0
    for passed in (True, False, True):
        a, b = update(a, b, passed)
    assert (a, b) == (4.0, 9.0)


def test_changing_a_consequence_assumption_cannot_move_a_posterior(
    contracts, observations, reported_at, scenario, root, tmp_path
):
    """Rewrite every monetary figure and re-estimate: the posteriors are the
    same, because inference never reads the scenario file."""
    from qair.risk import load_scenario
    import yaml

    before = estimate(contracts["fairness_parity_75"],
                      observations["fairness_parity_75"], reported_at)

    raw = yaml.safe_load((root / "risk_scenario.yaml").read_text())
    for m in raw["consequence"]:
        raw["consequence"][m]["median"] *= 1000
        raw["consequence"][m]["sigma"] *= 3
    for m in raw["escalation_probability"]:
        raw["escalation_probability"][m] = 0.9
    p = tmp_path / "risk_scenario.yaml"
    p.write_text(yaml.safe_dump(raw))
    loud = load_scenario(p)
    assert loud.consequence["fairness_parity_75"]["median"] != \
        scenario.consequence["fairness_parity_75"]["median"]

    after = estimate(contracts["fairness_parity_75"],
                     observations["fairness_parity_75"], reported_at)
    assert (before.alpha, before.beta) == (after.alpha, after.beta)
    assert before.mean == after.mean
    assert before.interval == after.interval
    assert before.band == after.band


def test_band_compares_the_interval_with_the_threshold():
    assert band_for(0.80, 0.95, 0.75) == "STRONG"
    assert band_for(0.10, 0.40, 0.75) == "WEAK"
    assert band_for(0.60, 0.90, 0.75) == "ADEQUATE"
    # A point estimate above the threshold whose interval straddles it is not STRONG.
    assert band_for(0.70, 0.90, 0.75) == "ADEQUATE"


def test_credible_interval_narrows_as_evidence_accumulates():
    widths = []
    for n in (10, 100, 1000):
        lo, hi = credible_interval(2 + 0.8 * n, 8 + 0.2 * n)
        widths.append(hi - lo)
    assert widths[0] > widths[1] > widths[2]


def test_too_few_observations_gives_insufficient_evidence(contracts, reported_at):
    c = contracts["fairness_parity_75"]
    few = [Observation(c.measure_id, c.evidence_type, True, reported_at)
           for _ in range(c.min_observations - 1)]
    st = estimate(c, few, reported_at)
    assert st.band == INSUFFICIENT_EVIDENCE
    assert st.reportable is False
    assert st.to_dict()["mean"] is None
    assert st.to_dict()["credible_interval"] is None


def test_stale_evidence_returns_insufficient_evidence(contracts, reported_at):
    c = contracts["fairness_parity_75"]
    old = reported_at - timedelta(days=c.max_age_days + 1)
    obs = [Observation(c.measure_id, c.evidence_type, True, old) for _ in range(20)]
    st = estimate(c, obs, reported_at)
    assert st.band == INSUFFICIENT_EVIDENCE
    assert "days old" in st.sufficiency.reason


def test_fresh_and_plentiful_evidence_is_sufficient(states):
    for mid, st in states.items():
        assert st.sufficiency.sufficient, f"{mid}: {st.sufficiency.reason}"


def test_prior_sensitivity_refits_three_priors(contracts, observations, reported_at):
    fits = prior_sensitivity(contracts["fairness_parity_75"],
                             observations["fairness_parity_75"], reported_at)
    assert set(fits) == {"Beta(1,1)", "Beta(2,8)", "Beta(8,2)"}
    # Same evidence in every fit; only the prior moves.
    counts = {(f.n_passed, f.n_failed) for f in fits.values()}
    assert len(counts) == 1


def test_estimation_is_per_measure(states):
    assert len(states) >= 2
    assert len({st.n_observations for st in states.values()}) > 1


def test_aggregation_is_reporting_only(states):
    from qair.inference import aggregate_for_reporting

    summary = aggregate_for_reporting(states)
    assert "reporting only" in summary["note"].lower()
    assert summary["n_measures"] == len(states)
