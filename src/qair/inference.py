"""Bayesian estimation of per-measure pass probabilities.

theta is the probability that a window meets its criterion. alpha counts windows
that met it, beta counts windows that did not, one observation per window.

The band compares the credible interval with the posterior threshold, so
ADEQUATE means the interval straddles it and the evidence does not classify the
measure either way. INSUFFICIENT_EVIDENCE replaces the band when the evidence
fails its volume or freshness requirement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

from scipy.stats import beta as beta_dist

from qair.contracts import ContractError, MeasurementContract
from qair.evidence import Observation, check_evidence_type
from qair.timeutil import to_utc

__all__ = [
    "PosteriorState",
    "Sufficiency",
    "BANDS",
    "INSUFFICIENT_EVIDENCE",
    "band_for",
    "credible_interval",
    "estimate",
    "prior_sensitivity",
    "update",
    "SENSITIVITY_PRIORS",
]

INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
BANDS: tuple[str, ...] = ("STRONG", "ADEQUATE", "WEAK", INSUFFICIENT_EVIDENCE)

#: Priors used for the sensitivity refit: uniform, the shipped prior, optimistic.
SENSITIVITY_PRIORS: dict[str, tuple[float, float]] = {
    "Beta(1,1)": (1.0, 1.0),
    "Beta(2,8)": (2.0, 8.0),
    "Beta(8,2)": (8.0, 2.0),
}


@dataclass(frozen=True)
class Sufficiency:
    """Whether the evidence behind an estimate meets its declared requirement."""

    sufficient: bool
    n_observations: int
    min_observations: int
    age_days: float | None
    max_age_days: int
    reason: str = ""


@dataclass(frozen=True)
class PosteriorState:
    """One measure's estimated state. The unit of ``posterior_state.json``."""

    measure_id: str
    estimand: str
    evidence_type: str
    prior_alpha: float
    prior_beta: float
    prior_mode: str
    alpha: float
    beta: float
    n_observations: int
    n_passed: int
    n_failed: int
    theta_threshold: float
    sufficiency: Sufficiency
    ci_level: float = 0.95
    observation_unit: str = ""

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def interval(self) -> tuple[float, float]:
        return credible_interval(self.alpha, self.beta, self.ci_level)

    @property
    def band(self) -> str:
        if not self.sufficiency.sufficient:
            return INSUFFICIENT_EVIDENCE
        lo, hi = self.interval
        return band_for(lo, hi, self.theta_threshold)

    @property
    def reportable(self) -> bool:
        """False when the measure returns INSUFFICIENT_EVIDENCE."""
        return self.sufficiency.sufficient

    def to_dict(self) -> dict[str, Any]:
        lo, hi = self.interval
        doc: dict[str, Any] = {
            "measure_id": self.measure_id,
            "estimand": self.estimand,
            "evidence_type": self.evidence_type,
            "prior": {
                "alpha": self.prior_alpha,
                "beta": self.prior_beta,
                "mode": self.prior_mode,
            },
            "posterior": {"alpha": round(self.alpha, 4), "beta": round(self.beta, 4)},
            "observations": {
                "n": self.n_observations,
                "passed": self.n_passed,
                "failed": self.n_failed,
                "unit": self.observation_unit,
            },
            "theta_threshold": self.theta_threshold,
            "band": self.band,
            "sufficiency": {
                "sufficient": self.sufficiency.sufficient,
                "n_observations": self.sufficiency.n_observations,
                "min_observations": self.sufficiency.min_observations,
                "evidence_age_days": (
                    None if self.sufficiency.age_days is None
                    else round(self.sufficiency.age_days, 2)
                ),
                "max_age_days": self.sufficiency.max_age_days,
                "reason": self.sufficiency.reason,
            },
        }
        if self.reportable:
            doc["mean"] = round(self.mean, 4)
            doc["credible_interval"] = [round(lo, 4), round(hi, 4)]
            doc["ci_level"] = self.ci_level
        else:
            # No band, and no point estimate either.
            doc["mean"] = None
            doc["credible_interval"] = None
            doc["ci_level"] = self.ci_level
        return doc


def update(alpha: float, beta: float, passed: bool) -> tuple[float, float]:
    """Beta-Binomial update. One window is one observation.

    Consequence is deliberately absent: it is modelled in qair.risk. Weighting an
    observation by its cost here would add pseudo-observations and change both the
    estimate and its interval.
    """
    return (alpha + 1.0, beta) if passed else (alpha, beta + 1.0)


def credible_interval(alpha: float, beta: float, level: float = 0.95) -> tuple[float, float]:
    """Equal-tailed Bayesian credible interval."""
    tail = (1.0 - level) / 2.0
    return (
        float(beta_dist.ppf(tail, alpha, beta)),
        float(beta_dist.ppf(1.0 - tail, alpha, beta)),
    )


def band_for(lo: float, hi: float, theta_threshold: float) -> str:
    """STRONG above the threshold, WEAK below, ADEQUATE straddling."""
    if lo >= theta_threshold:
        return "STRONG"
    if hi <= theta_threshold:
        return "WEAK"
    return "ADEQUATE"


def _sufficiency(
    contract: MeasurementContract,
    observations: Sequence[Observation],
    reported_at: datetime,
) -> Sufficiency:
    n = len(observations)
    dated = [o.observed_at for o in observations if o.observed_at is not None]
    age = None
    if dated:
        age = (to_utc(reported_at) - max(dated)).total_seconds() / 86400.0

    if n < contract.min_observations:
        return Sufficiency(
            False, n, contract.min_observations, age, contract.max_age_days,
            f"{n} observations, below the minimum of {contract.min_observations}",
        )
    if age is None:
        return Sufficiency(
            False, n, contract.min_observations, None, contract.max_age_days,
            "no observation carries a date, so freshness cannot be established",
        )
    if age > contract.max_age_days:
        return Sufficiency(
            False, n, contract.min_observations, age, contract.max_age_days,
            f"newest evidence is {age:.1f} days old, past the maximum of "
            f"{contract.max_age_days} days",
        )
    return Sufficiency(True, n, contract.min_observations, age, contract.max_age_days, "")


def estimate(
    contract: MeasurementContract,
    observations: Iterable[Observation],
    reported_at: datetime,
    prior: tuple[float, float] | None = None,
    ci_level: float = 0.95,
) -> PosteriorState:
    """Estimate one measure's posterior from its observations."""
    obs = list(observations)
    for o in obs:
        check_evidence_type(contract, o)

    a0, b0 = prior if prior is not None else contract.prior
    a, b = a0, b0
    for o in obs:
        a, b = update(a, b, o.passed)

    n_pass = sum(1 for o in obs if o.passed)
    return PosteriorState(
        measure_id=contract.measure_id,
        estimand=contract.estimand,
        evidence_type=contract.evidence_type,
        prior_alpha=a0,
        prior_beta=b0,
        prior_mode=contract.prior_mode,
        alpha=a,
        beta=b,
        n_observations=len(obs),
        n_passed=n_pass,
        n_failed=len(obs) - n_pass,
        theta_threshold=contract.theta_threshold,
        sufficiency=_sufficiency(contract, obs, reported_at),
        ci_level=ci_level,
        observation_unit=contract.window,
    )


def prior_sensitivity(
    contract: MeasurementContract,
    observations: Iterable[Observation],
    reported_at: datetime,
    priors: Mapping[str, tuple[float, float]] | None = None,
) -> dict[str, PosteriorState]:
    """Refit the same observations under several priors."""
    obs = list(observations)
    chosen = dict(priors) if priors is not None else dict(SENSITIVITY_PRIORS)
    return {
        label: estimate(contract, obs, reported_at, prior=p)
        for label, p in chosen.items()
    }


def aggregate_for_reporting(states: Mapping[str, PosteriorState]) -> dict[str, Any]:
    """Summary across measures, for reporting only. Never used as an input."""
    reportable = [s for s in states.values() if s.reportable]
    if not reportable:
        raise ContractError(
            "No measure has sufficient evidence; there is nothing to summarise."
        )
    return {
        "n_measures": len(states),
        "n_reportable": len(reportable),
        "n_insufficient": len(states) - len(reportable),
        "unweighted_mean_of_means": round(
            sum(s.mean for s in reportable) / len(reportable), 4
        ),
        "bands": {s.measure_id: s.band for s in states.values()},
        "note": "Reporting only; each measure is estimated independently.",
    }
