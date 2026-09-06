"""Simulation invariants: sampling, dependence, escalation, exclusion."""

from __future__ import annotations

import numpy as np
import pytest

from qair.risk import apply_counterfactual, hold_healthy, simulate, validate_dependence

SMALL = 4000          # enough to be stable for structural assertions, fast enough for CI


def test_theta_is_sampled_not_averaged():
    """Two states with the same mean and different spreads must price differently."""
    from qair.contracts import load_contracts
    from qair.risk import load_scenario
    from dataclasses import replace

    contracts = load_contracts()
    scenario = load_scenario()
    from qair.inference import PosteriorState, Sufficiency

    def state(mid, a, b):
        c = contracts[mid]
        return PosteriorState(
            measure_id=mid, estimand=c.estimand, evidence_type=c.evidence_type,
            prior_alpha=2.0, prior_beta=8.0, prior_mode="illustrative",
            alpha=a, beta=b, n_observations=50, n_passed=25, n_failed=25,
            theta_threshold=c.theta_threshold,
            sufficiency=Sufficiency(True, 50, 8, 1.0, 30, ""),
        )

    tight = {m: state(m, 500.0, 500.0) for m in contracts}
    wide = {m: state(m, 1.0, 1.0) for m in contracts}
    assert abs(tight["fairness_parity_75"].mean - wide["fairness_parity_75"].mean) < 1e-9

    t = simulate(tight, contracts, scenario, n=SMALL, seed=7)
    w = simulate(wide, contracts, scenario, n=SMALL, seed=7)
    assert t.tce != w.tce, "identical means with different spreads priced identically"


def test_the_copula_is_applied_to_the_theta_draws(states, scenario):
    """The realised correlation of the sampled thetas matches the declared matrix."""
    import numpy as np
    from scipy.stats import beta as beta_dist
    from scipy.stats import norm

    n = 200_000
    order = scenario.dependence_order
    rng = np.random.default_rng(1)
    L = np.linalg.cholesky(scenario.dependence_matrix)
    u = norm.cdf(rng.standard_normal((n, 6)) @ L.T)
    theta = np.column_stack(
        [beta_dist.ppf(u[:, j], states[m].alpha, states[m].beta) for j, m in enumerate(order)]
    )

    realised = np.corrcoef(theta.T)
    for i in range(6):
        for j in range(i + 1, 6):
            declared = scenario.dependence_matrix[i, j]
            assert abs(realised[i, j] - declared) < 0.05, (
                f"{order[i]}/{order[j]}: declared {declared}, realised {realised[i, j]:.3f}"
            )

    # One underlying event moves several measures at once.
    d, f = order.index("drift_distance_50"), order.index("fairness_parity_75")
    med = np.median(theta, axis=0)
    joint = float(((theta[:, d] < med[d]) & (theta[:, f] < med[f])).mean())
    assert joint > 0.30, f"joint low-theta share {joint:.3f}; independence would give 0.25"


def test_dependence_barely_moves_this_loss_tail(states, contracts, scenario):
    """With these parameters, dependence has almost no effect on the loss tail.

    A month becomes extreme here through one heavy lognormal draw rather than
    through several measures breaching together, so correlating theta changes the
    TCE by far less than the seed spread. Pinned so the result cannot drift
    unnoticed; see docs/risk-model.md.
    """
    from dataclasses import replace

    import numpy as np

    independent = replace(scenario, dependence_matrix=np.eye(6))
    dep = simulate(states, contracts, scenario, n=200_000, seed=11)
    ind = simulate(states, contracts, independent, n=200_000, seed=11)
    ratio = dep.tce / ind.tce
    assert 0.97 < ratio < 1.05, (
        f"dependent/independent TCE ratio is {ratio:.3f}, outside the band this "
        f"configuration has held. docs/risk-model.md documents the current result "
        f"and needs revisiting."
    )


def test_escalation_produces_mass_at_zero(baseline):
    assert baseline.zero_loss_share > 0.0
    assert (baseline.total_losses == 0).sum() > 0


def test_removing_escalation_removes_the_mass_at_zero(states, contracts, scenario):
    from dataclasses import replace

    always = replace(
        scenario,
        escalation_probability={m: 1.0 for m in scenario.escalation_probability},
    )
    with_escalation = simulate(states, contracts, scenario, n=SMALL, seed=3)
    without = simulate(states, contracts, always, n=SMALL, seed=3)
    assert without.zero_loss_share == 0.0
    assert with_escalation.zero_loss_share > 0.0


def test_exposure_comes_from_the_contract(scenario, contracts):
    v = scenario.monthly_decisions
    assert scenario.exposure_windows(contracts["fairness_parity_75"]) == v // 75
    assert scenario.exposure_windows(contracts["data_quality_50"]) == v // 50


def test_scenario_file_declares_illustrative_mode(scenario):
    assert scenario.mode == "illustrative"


def test_dependence_matrix_is_declared_not_estimated(scenario):
    assert scenario.dependence_source == "declared"


def test_var_and_tce_are_ordered(baseline):
    assert baseline.tce >= baseline.var >= baseline.median_loss


def test_insufficient_measures_are_excluded_not_imputed(
    states, contracts, scenario, register, reported_at
):
    """A measure with no usable evidence contributes no loss and is named."""
    modified = apply_counterfactual("missing_documentation", states, scenario,
                              contracts=contracts, control_register=register,
                              reported_at=reported_at)
    assert modified["control_execution"].band == "INSUFFICIENT_EVIDENCE"
    run = simulate(modified, contracts, scenario, n=SMALL, seed=5)
    assert "control_execution" in run.excluded_measures
    assert "control_execution" not in run.measures


def test_every_measure_insufficient_raises(states, contracts, scenario):
    from dataclasses import replace
    from qair.contracts import ContractError
    from qair.inference import Sufficiency

    dead = {
        m: replace(st, sufficiency=Sufficiency(False, 0, 8, None, 30, "no evidence"))
        for m, st in states.items()
    }
    with pytest.raises(ContractError, match="INSUFFICIENT_EVIDENCE"):
        simulate(dead, contracts, scenario, n=100)


def test_hold_healthy_replaces_only_the_named_measure(states, scenario):
    held = hold_healthy(states, "fairness_parity_75", scenario)
    assert (held["fairness_parity_75"].alpha, held["fairness_parity_75"].beta) == \
        scenario.healthy_state
    for m in states:
        if m != "fairness_parity_75":
            assert held[m] is states[m]


# ---------------------------------------------------------------------------
# Dependence matrix validation
# ---------------------------------------------------------------------------

def _matrix(rows):
    import numpy as np
    return np.array(rows, dtype=float)


@pytest.mark.parametrize("matrix, order, message", [
    (_matrix([[1.0, 0.2, 0.0], [0.2, 1.0, 0.0]]), ["a", "b", "c"], "square"),
    (_matrix([[1.0, 0.2], [0.2, 1.0]]), ["a", "b", "c"], "names 3 measures"),
    (_matrix([[1.0, 0.2], [0.5, 1.0]]), ["a", "b"], "not symmetric"),
    (_matrix([[0.9, 0.2], [0.2, 1.0]]), ["a", "b"], "diagonal"),
    (_matrix([[1.0, 1.4], [1.4, 1.0]]), ["a", "b"], r"\[-1, 1\]"),
    (_matrix([[1.0, 0.9, -0.9], [0.9, 1.0, 0.9], [-0.9, 0.9, 1.0]]),
     ["a", "b", "c"], "positive definite"),
])
def test_invalid_dependence_matrices_are_rejected(matrix, order, message):
    from qair.contracts import ContractError

    with pytest.raises(ContractError, match=message):
        validate_dependence(matrix, order)


def test_duplicate_measures_in_dependence_order_are_rejected():
    from qair.contracts import ContractError

    with pytest.raises(ContractError, match="duplicates"):
        validate_dependence(_matrix([[1.0, 0.2], [0.2, 1.0]]), ["a", "a"])


def test_the_shipped_matrix_validates(scenario):
    validate_dependence(scenario.dependence_matrix, scenario.dependence_order)


def test_seed_stability_reports_a_spread(stability):
    assert len(stability["seeds"]) == 8
    for key in ("expected_loss", "var", "tce"):
        assert stability[key]["relative_spread"] >= 0
        assert len(stability[key]["values"]) == 8
