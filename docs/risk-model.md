# Risk model

Frequency comes from the posteriors. Cost comes from `risk_scenario.yaml`. They
are multiplied, not fitted to each other, and there is no curve between a
posterior and a loss.

## Per simulated month, per measure

1. Sample theta from the posterior. Sampling rather than averaging is what carries
   estimation uncertainty into the loss figures.
2. `1 - theta` is the chance one exposure window breaches its criterion.
3. Breaches ~ Binomial(exposure windows, 1 - theta).
4. Loss-bearing events ~ Binomial(breaches, escalation probability).
5. Cost ~ Lognormal(median, sigma) per event, summed.

## Exposure

Derived, not declared twice: monthly volume from the scenario file, window length
from the contract.

| Measure | Window | Windows/month at 40,000 decisions |
|---|---|---|
| `performance_per_decision` | 1 decision | 40,000 |
| `data_quality_50` | 50 decisions | 800 |
| `drift_distance_50` | 50 decisions | 800 |
| `fairness_parity_75` | 75 decisions | 533 |
| `security_authz_50` | 50 decisions | 800 |
| `control_execution` | 1 control instance | 8 |

## Escalation

Most criterion breaches do not become incidents. Without this step the model
produces a loss every month, and the loss distribution has no mass at zero.

`test_removing_escalation_removes_the_mass_at_zero` sets every escalation
probability to 1 and asserts the zero mass disappears.

## Dependence

A Gaussian copula on the theta draws. The matrix is validated on load: square,
matching `dependence.order`, symmetric, unit diagonal, entries in [-1, 1], and
positive definite. An invalid matrix raises `ContractError` naming the problem.

`source: declared` means the values are assumed rather than estimated from
incident history.

**In this configuration the copula makes almost no difference to the loss tail.**
Dependent and independent sampling give 95% TCEs within about 0.2% of each other
at 200,000 months, far inside the seed spread. A month becomes extreme here
through one heavy lognormal draw rather than through several measures breaching
together: exposure counts are in the hundreds so breach counts average out, and
the escalation step leaves a small event count whose draws are independent given
theta.

Flattening every sigma to 0.3 gives a ratio of 1.005; raising every escalation
probability to 0.02 gives 1.005; both together give 1.019. The copula is still the
right place for dependence, and it does show up in the theta draws
— `test_the_copula_is_applied_to_the_theta_draws` checks the realised correlations
against the declared matrix — but it is not what drives this tail.
`test_dependence_barely_moves_this_loss_tail` pins the result.

## Simulation size and seeds

50,000 months, eight stability seeds. At 10,000 the TCE moved about 19% across
seeds. Measured at 50,000:

| Statistic | Spread across seeds |
|---|---|
| Expected loss | ~3% |
| 95% VaR | ~1% |
| 95% TCE | ~11% |

The TCE spread sets the precision floor. A difference smaller than it is not a
result, and every tolerance in `tests/test_reproducibility.py` derives from it.

## Statistics

VaR is the 95th percentile of monthly loss; TCE is the mean above it. Both are
needed because this distribution is bimodal — mostly small, occasionally large —
so VaR alone hides the shape.

## Tail attribution

Two views: which measures the worst 5% of months are made of, and what happens to
the TCE when one measure is held at a healthy state.

Holding a measure healthy overwrites its posterior. It is a counterfactual, not
evidence, and answers "what if this had a long clean record" rather than "what if
we fixed it next quarter".

The two rankings differ, because the measure contributing most to the tail is not
the one with the highest mean cost.

## Counterfactual scenarios

Declared in `risk_scenario.yaml`. Each modifies the estimated posterior state and
re-runs the same model. They are not evidence and are only comparable with each
other.

| Scenario | What changes |
|---|---|
| `baseline` | nothing |
| `drift_spike` | two more failing drift windows |
| `fairness_degradation` | twelve more failing parity windows |
| `monitoring_gap` | nothing; stale evidence cannot move a posterior, so this matches baseline by construction |
| `missing_documentation` | the control register ages past its freshness requirement |

`missing_documentation` is the one worth reading closely. `control_execution`
returns `INSUFFICIENT_EVIDENCE` and is excluded from the loss sum rather than
imputed, so the reported loss falls by about 10%. That fall is a measure becoming
unmeasurable, not an improvement. The gate still fails, because
`INSUFFICIENT_EVIDENCE` maps to `HOLD`.

## Everything monetary is illustrative

`mode: illustrative` means no parameter here is calibrated from incident history.
Escalation probability and monthly volume together set the magnitude of every
figure; Notebook 3 shows how much moves when they do. See
[`assumptions.md`](assumptions.md).
