# Exercises

Optional. Each one works on the repository as it stands and needs no other
material.

## 1. Add a measure

The example ships six. Nothing in `src/qair` assumes that number.

1. Write `contracts/<your_measure>.json`. Copy an existing one and change the
   estimand, the observable fields, the window, the criterion and the parameters.
2. Add a function to `measures.py` and register it in `MEASURE_FUNCTIONS`. It takes
   `(records, contract, **context)` and returns a list of `Observation`.
3. Add the measure to `escalation_probability`, `consequence` and
   `dependence.order` in `risk_scenario.yaml`, and extend the dependence matrix by
   one row and column. The matrix is validated on load, so an asymmetric or
   non-positive-definite edit will fail with a message saying which.
4. Run all three notebooks.

`tests/test_add_a_measure.py` does exactly this for a tail-latency measure, with
the contract in `tests/fixtures/contracts/` and the function in
`tests/fixtures/extra_measures.py`. Copy those two files as a starting point.

Other candidates visible in the data: per-caller volume anomaly
(`measures.caller_volume_share` computes the statistic and nothing scores it), or
abstention rate.

## 2. Justify a threshold

Pick one measure and write down, in a few sentences:

- what risk the criterion threshold guards against;
- what the posterior threshold means for how often you are willing to be wrong;
- what would have to change before you would revise either.

Then set both in the contract and re-run Notebook 2. The threshold sensitivity
table shows which bands move and what the gate returns.

There is no procedure that derives a threshold from the measurement. Recording the
reasoning next to the value is the point.

## 3. Detect contradictions systematically

`qair.evidence.divergences` reports controls recorded as run whose covered measure
reads WEAK. Extend it:

- What should be reported when a control covers no measure at all?
- Is `NO_EVIDENCE` beside a STRONG measure a finding?
- What do you report when the measure is `INSUFFICIENT_EVIDENCE` and the control
  says EVIDENCED? Neither contradicts the other and something is still wrong.

Rank the results. The width of the gap, the band, and the observation count behind
the measure are all defensible bases, and they give different orders.

## 4. Calibrate the loss model

`risk_scenario.yaml` is in `mode: illustrative`. Moving it to `calibrated` needs
two counts from your own records over the same period:

- criterion breaches, from monitoring;
- incidents, from the incident register.

Their ratio is the escalation probability. Costs come from your incident history.
Until both exist, leave the mode alone: Notebook 3 reports every figure as
illustrative and the schema rejects any other claim.

## 5. Replace the telemetry

`measures.py` is the only file that knows anything about credit decisioning.
Point the pipeline at a stream of your own by writing records with the fields in
`qair.telemetry.RECORD_SCHEMA`, or by changing the schema and the measurement
functions together.
