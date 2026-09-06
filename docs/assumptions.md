# Assumptions

What each assumption is, where it lives, and what would replace it.

## Statistical

**Prior — Beta(2, 8), mean 0.20.** A conservative start for a measure with no
validated history. In `contracts/*.json` → `prior`, marked `illustrative`.
Notebook 2 refits under Beta(1,1) and Beta(8,2) and reports which bands move. On
the example stream, `data_quality_50` and `control_execution` change band, so
neither conclusion is carried by the data alone.

**Window lengths — 1, 50, 75 decisions.** In each contract. They set the
observation count, and therefore the interval width, for that measure.

**Fairness criterion — parity ratio ≥ 0.80.** The four-fifths ratio, a screening
heuristic from employment selection rather than a general fairness standard.
Note this is separate from the operating bands you might use to colour a chart;
the criterion is what decides whether a window passes.

**Posterior thresholds — 0.90 for fairness, 0.75 elsewhere.** The share of windows
that must pass. Both are choices; nothing derives them.

**Laplace smoothing in the parity ratio.** A 75-decision window can leave a group
with very few decisions, and an unsmoothed ratio then turns on one outcome. In
`contracts/fairness_parity_75.json` → `parameters.smoothing`. It biases the ratio
slightly upward in small windows, which makes a real disparity look milder.

**Sufficiency — 8 observations and 30 days, 5 for `control_execution`.** Below
about 8 Beta-Binomial observations the band follows the prior. Thirty days is one
reporting cycle. `control_execution` has a lower floor because the register holds
eight controls in total.

## Monetary

All in `risk_scenario.yaml`, all `mode: illustrative`.

**Escalation probability.** The chance one criterion breach becomes a
loss-bearing event, from 1 in 100,000 for a single slow decision to 1 in 20 for an
unevidenced control. **These are the least grounded numbers here and the main
lever on total magnitude.** Replace them with a breach count from monitoring and
an incident count from your incident register over the same period; the ratio is
the escalation probability.

**Consequence distributions.** Lognormal median and sigma per measure. Sigma
decides which measure dominates the tail and matters more than the median.
Calibrate from incident history, insurance data or legal exposure assessments.

**Monthly volume — 40,000 decisions.** Scales the whole loss distribution roughly
linearly. Replace it with your own before reading any figure.

**Dependence matrix.** `source: declared` — assumed, not estimated. Validated on
load for shape, symmetry, diagonal, range and positive-definiteness. In this
configuration it barely affects the loss tail; see
[`risk-model.md`](risk-model.md).

**Healthy counterfactual — Beta(95, 5).** The state a measure is held at for
attribution. A what-if, not a target.

**Simulation size — 50,000 months, 8 seeds.** At 10,000 the TCE moved about 19%
across seeds. The measured spread is a property of this loss distribution; re-run
`seed_stability` after changing the consequence parameters.

## Data

**The generator.** `qair.telemetry.gen_applicants` produces synthetic applicants;
with `drifted=True` incomes shift and the shift falls hardest on groups C and D.
The disparity is injected deliberately, so the fairness result is a property of
the generator, not a finding.

Everything transferable is in the schema, the contracts, the evidence model and
the engine. The numbers are not.

**scikit-learn version.** Model coefficients could shift between releases and move
a window outcome. Tested across 1.7.2 and 1.9.0 they did not. The tests read a
committed fixture regardless, so they do not depend on it.
