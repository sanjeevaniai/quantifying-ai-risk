"""Monte Carlo loss simulation from per-measure posteriors.

Per simulated month, per measure:

1. Sample theta from the posterior (sampled, not averaged, so the uncertainty in
   the estimate reaches the output).
2. ``1 - theta`` is the chance a single exposure window breaches its criterion.
3. Breaches are Binomial over the declared number of exposure windows.
4. Each breach becomes a loss-bearing event with a declared escalation probability.
5. Draw a lognormal consequence per event and sum the month.

Dependence is a Gaussian copula on the theta draws. Frequency comes from the
posteriors; consequence comes from risk_scenario.yaml. They are multiplied, never
fitted to each other.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import yaml
from scipy.stats import beta as beta_dist
from scipy.stats import norm

from qair.contracts import ContractError, MeasurementContract
from qair.inference import PosteriorState

__all__ = [
    "RiskResult",
    "RiskScenario",
    "apply_counterfactual",
    "hold_healthy",
    "load_scenario",
    "scenario_path",
    "seed_stability",
    "simulate",
    "tail_attribution",
    "validate_dependence",
]


def scenario_path(start: Path | str | None = None) -> Path:
    here = Path(start) if start is not None else Path(__file__).resolve()
    for candidate in [here, *here.parents]:
        target = candidate / "risk_scenario.yaml"
        if target.is_file():
            return target
    raise FileNotFoundError("No risk_scenario.yaml found above " + str(here))


def validate_dependence(matrix: np.ndarray, order: Sequence[str]) -> None:
    """Check that a declared dependence matrix can be used as a copula correlation.

    Raises ContractError naming the problem: shape, symmetry, unit diagonal,
    correlation range, or a matrix that is not positive definite.
    """
    n = len(order)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ContractError(
            f"dependence.matrix must be square, got shape {matrix.shape}"
        )
    if matrix.shape[0] != n:
        raise ContractError(
            f"dependence.matrix is {matrix.shape[0]}x{matrix.shape[0]} but "
            f"dependence.order names {n} measures"
        )
    if len(set(order)) != n:
        raise ContractError("dependence.order contains duplicates")
    if not np.allclose(matrix, matrix.T, atol=1e-9):
        raise ContractError("dependence.matrix is not symmetric")
    if not np.allclose(np.diag(matrix), 1.0, atol=1e-9):
        raise ContractError("dependence.matrix must have 1.0 on the diagonal")
    if matrix.min() < -1.0 or matrix.max() > 1.0:
        raise ContractError("dependence.matrix entries must lie in [-1, 1]")
    try:
        np.linalg.cholesky(matrix)
    except np.linalg.LinAlgError as exc:
        eigenvalues = np.linalg.eigvalsh(matrix)
        raise ContractError(
            f"dependence.matrix is not positive definite "
            f"(smallest eigenvalue {eigenvalues.min():.4f}); it cannot be used as "
            f"a copula correlation"
        ) from exc


@dataclass(frozen=True)
class RiskScenario:
    """Monetary and exposure parameters, loaded from risk_scenario.yaml."""

    mode: str
    reporting_period: str
    reported_at: str
    currency: str
    monthly_decisions: int
    control_instances_per_month: int
    escalation_probability: dict[str, float]
    consequence: dict[str, dict[str, float]]
    dependence_order: tuple[str, ...]
    dependence_matrix: np.ndarray
    dependence_source: str
    n_simulations: int
    primary_seed: int
    stability_seeds: tuple[int, ...]
    var_level: float
    healthy_state: tuple[float, float]
    scenarios: dict[str, dict[str, Any]]
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def exposure_windows(self, contract: MeasurementContract) -> int:
        return contract.exposure_windows(
            self.monthly_decisions, self.control_instances_per_month
        )

    def check_covers(self, contracts: Mapping[str, MeasurementContract]) -> None:
        """Check the scenario declares a parameter set for every loaded measure."""
        measures = set(contracts)
        for name, declared in (
            ("dependence.order", set(self.dependence_order)),
            ("escalation_probability", set(self.escalation_probability)),
            ("consequence", set(self.consequence)),
        ):
            missing = measures - declared
            extra = declared - measures
            if missing or extra:
                raise ContractError(
                    f"risk_scenario.yaml {name} does not match contracts/: "
                    f"missing {sorted(missing)}, unknown {sorted(extra)}"
                )


def load_scenario(path: Path | str | None = None) -> RiskScenario:
    p = Path(path) if path is not None else scenario_path()
    raw = yaml.safe_load(p.read_text())
    dep, sim = raw["dependence"], raw["simulation"]
    order = tuple(dep["order"])
    matrix = np.array(dep["matrix"], dtype=float)
    validate_dependence(matrix, order)
    return RiskScenario(
        mode=raw["mode"],
        reporting_period=raw["reporting_period"],
        reported_at=raw["reported_at"],
        currency=raw["currency"],
        monthly_decisions=int(raw["exposure"]["monthly_decisions"]),
        control_instances_per_month=int(raw["exposure"]["control_instances_per_month"]),
        escalation_probability=dict(raw["escalation_probability"]),
        consequence={k: dict(v) for k, v in raw["consequence"].items()},
        dependence_order=order,
        dependence_matrix=matrix,
        dependence_source=dep["source"],
        n_simulations=int(sim["n_simulations"]),
        primary_seed=int(sim["primary_seed"]),
        stability_seeds=tuple(int(s) for s in sim["stability_seeds"]),
        var_level=float(sim["var_level"]),
        healthy_state=(
            float(raw["counterfactual"]["healthy_state"]["alpha"]),
            float(raw["counterfactual"]["healthy_state"]["beta"]),
        ),
        scenarios={k: dict(v) for k, v in raw["scenarios"].items()},
        raw=raw,
    )


@dataclass
class RiskResult:
    """One simulated loss distribution and the statistics read off it."""

    measures: tuple[str, ...]
    total_losses: np.ndarray
    per_measure_losses: np.ndarray
    excluded_measures: tuple[str, ...]
    n_simulations: int
    seed: int
    var_level: float

    @property
    def expected_loss(self) -> float:
        return float(self.total_losses.mean())

    @property
    def median_loss(self) -> float:
        return float(np.median(self.total_losses))

    @property
    def var(self) -> float:
        return float(np.percentile(self.total_losses, self.var_level * 100))

    @property
    def tce(self) -> float:
        tail = self.total_losses[self.total_losses >= self.var]
        return float(tail.mean()) if tail.size else 0.0

    @property
    def zero_loss_share(self) -> float:
        return float((self.total_losses == 0).mean())

    def expected_by_measure(self) -> dict[str, float]:
        return {
            m: float(self.per_measure_losses[:, j].mean())
            for j, m in enumerate(self.measures)
        }

    def tail_shares(self) -> dict[str, float]:
        """Share of the loss in the worst ``1 - var_level`` of months, by measure."""
        tail_avg = self.per_measure_losses[self.total_losses >= self.var].mean(axis=0)
        total = tail_avg.sum()
        if total == 0:
            return {m: 0.0 for m in self.measures}
        return {m: float(tail_avg[j] / total) for j, m in enumerate(self.measures)}


def simulate(
    states: Mapping[str, PosteriorState],
    contracts: Mapping[str, MeasurementContract],
    scenario: RiskScenario,
    seed: int | None = None,
    n: int | None = None,
) -> RiskResult:
    """Run the loss model.

    Measures whose evidence is insufficient are excluded rather than imputed, so
    the reported total falls. ``RiskResult.excluded_measures`` names them.
    """
    n = int(n or scenario.n_simulations)
    seed = scenario.primary_seed if seed is None else int(seed)
    rng = np.random.default_rng(seed)

    ordered = [m for m in scenario.dependence_order if m in states]
    excluded = tuple(m for m in ordered if not states[m].reportable)
    active = [m for m in ordered if states[m].reportable]
    if not active:
        raise ContractError("Every measure is INSUFFICIENT_EVIDENCE; nothing to simulate")

    idx = [scenario.dependence_order.index(m) for m in active]
    corr = scenario.dependence_matrix[np.ix_(idx, idx)]
    validate_dependence(corr, active)
    lower = np.linalg.cholesky(corr)

    z = rng.standard_normal((n, len(active))) @ lower.T
    u = np.clip(norm.cdf(z), 1e-12, 1 - 1e-12)

    per_measure = np.zeros((n, len(active)))
    for j, m in enumerate(active):
        st = states[m]
        theta = beta_dist.ppf(u[:, j], st.alpha, st.beta)
        windows = scenario.exposure_windows(contracts[m])
        breaches = rng.binomial(windows, np.clip(1.0 - theta, 0.0, 1.0))
        events = rng.binomial(breaches, float(scenario.escalation_probability[m]))
        total_events = int(events.sum())
        if total_events:
            c = scenario.consequence[m]
            draws = np.exp(
                np.log(float(c["median"]))
                + float(c["sigma"]) * rng.standard_normal(total_events)
            )
            per_measure[:, j] = np.bincount(
                np.repeat(np.arange(n), events), weights=draws, minlength=n
            )

    return RiskResult(
        measures=tuple(active),
        total_losses=per_measure.sum(axis=1),
        per_measure_losses=per_measure,
        excluded_measures=excluded,
        n_simulations=n,
        seed=seed,
        var_level=scenario.var_level,
    )


def seed_stability(
    states: Mapping[str, PosteriorState],
    contracts: Mapping[str, MeasurementContract],
    scenario: RiskScenario,
    seeds: Sequence[int] | None = None,
    n: int | None = None,
) -> dict[str, Any]:
    """Re-run under several seeds and report the spread of each statistic."""
    seeds = list(seeds or scenario.stability_seeds)
    runs = [simulate(states, contracts, scenario, seed=s, n=n) for s in seeds]
    out: dict[str, Any] = {"seeds": seeds, "n_simulations": runs[0].n_simulations}
    for name, values in (
        ("expected_loss", [r.expected_loss for r in runs]),
        ("var", [r.var for r in runs]),
        ("tce", [r.tce for r in runs]),
    ):
        arr = np.array(values, dtype=float)
        out[name] = {
            "values": [float(v) for v in arr],
            "mean": float(arr.mean()),
            "min": float(arr.min()),
            "max": float(arr.max()),
            "relative_spread": float((arr.max() - arr.min()) / arr.mean()) if arr.mean() else 0.0,
        }
    return out


def hold_healthy(
    states: Mapping[str, PosteriorState],
    measure_id: str,
    scenario: RiskScenario,
) -> dict[str, PosteriorState]:
    """Counterfactual: replace one measure's posterior with the declared healthy state.

    This overwrites an estimate. It is a what-if, not evidence ingestion, and its
    output is only comparable with other counterfactual runs.
    """
    a, b = scenario.healthy_state
    out = dict(states)
    out[measure_id] = replace(out[measure_id], alpha=a, beta=b)
    return out


def tail_attribution(
    states: Mapping[str, PosteriorState],
    contracts: Mapping[str, MeasurementContract],
    scenario: RiskScenario,
    baseline: RiskResult | None = None,
) -> dict[str, Any]:
    """Decompose the tail by share, and by holding each measure healthy in turn."""
    base = baseline or simulate(states, contracts, scenario)
    held = {}
    for m in base.measures:
        run = simulate(hold_healthy(states, m, scenario), contracts, scenario)
        held[m] = {
            "tce": run.tce,
            "tce_change": (run.tce - base.tce) / base.tce if base.tce else 0.0,
            "expected_loss": run.expected_loss,
        }
    return {
        "var_level": scenario.var_level,
        "baseline_tce": base.tce,
        "tail_share": base.tail_shares(),
        "expected_by_measure": base.expected_by_measure(),
        "hold_healthy": held,
        "note": "Counterfactual. Interpret a change only if it exceeds the seed spread.",
    }


def apply_counterfactual(
    name: str,
    states: Mapping[str, PosteriorState],
    scenario: RiskScenario,
    *,
    contracts: Mapping[str, MeasurementContract] | None = None,
    control_register: Any | None = None,
    reported_at: datetime | None = None,
) -> dict[str, PosteriorState]:
    """Apply a declared counterfactual scenario to the estimated state.

    These scenarios modify posteriors directly to answer "what if the state were
    different". They are not evidence: nothing here observes anything, and the
    results are only comparable with each other.
    """
    spec = scenario.scenarios.get(name)
    if spec is None:
        raise ContractError(f"No scenario named {name!r} in risk_scenario.yaml")
    mod = spec.get("modification", "none")
    out = dict(states)

    if mod in (None, "none"):
        # baseline, and monitoring_gap: stale evidence cannot move a posterior,
        # so the monitoring-gap row is identical to baseline by construction.
        return out

    if mod == "add_failing_windows":
        m, k = spec["measure"], int(spec["n_windows"])
        st = out[m]
        out[m] = replace(
            st,
            beta=st.beta + k,
            n_observations=st.n_observations + k,
            n_failed=st.n_failed + k,
        )
        return out

    if mod == "stale_control_register":
        if contracts is None or control_register is None or reported_at is None:
            raise ContractError(
                "stale_control_register needs contracts, control_register and reported_at"
            )
        from qair.inference import estimate

        m = spec["measure"]
        aged = control_register.aged(int(spec["register_age_days"]))
        out[m] = estimate(contracts[m], aged.observations(contracts[m]), reported_at)
        return out

    raise ContractError(f"Unknown scenario modification {mod!r}")
