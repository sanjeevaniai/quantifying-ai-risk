# Measurement contracts

One JSON file per measure in [`../contracts/`](../contracts), validated against
[`measurement_contract.schema.json`](../schemas/measurement_contract.schema.json).

The contract declares the measure before it is computed, so a reader can tell
what a number means without reading the code.

## Fields

| Field | Purpose |
|---|---|
| `measure_id` | Identifier, matching the filename |
| `construct` | What is being measured, in words |
| `estimand` | What the number estimates, stated precisely |
| `evidence_type` | `system_behavior` or `control`. Enforced at estimation time |
| `observable_fields` | Which record fields the measurement function may read |
| `window` | `{length, unit}`. Sets the observation count per unit of data |
| `measurement_function` | The statistic, in words. Implemented in `measures.py` |
| `parameters` | Constants the statistic reads, so they are written down once |
| `operator`, `threshold` | What makes one window pass |
| `theta_threshold` | Share of windows that must pass; the band boundary |
| `prior` | `alpha`, `beta`, and whether the values are illustrative or calibrated |
| `sufficiency` | `min_observations` and `max_age_days` before the measure will report |
| `owner` | Accountable role, not a named individual |
| `limitations` | Where the number stops being reliable |

## The six in the example

| `measure_id` | Evidence | Window | Passes when | Posterior threshold |
|---|---|---|---|---|
| `performance_per_decision` | behaviour | 1 decision | confidence ≥ 0.70, latency ≤ 300 ms, no error | 0.75 |
| `data_quality_50` | behaviour | 50 decisions | share passing all input checks ≥ 0.98 | 0.75 |
| `drift_distance_50` | behaviour | 50 decisions | normalised distance ≤ 0.10 | 0.75 |
| `fairness_parity_75` | behaviour | 75 decisions | min group rate / reference rate ≥ 0.80 | 0.90 |
| `security_authz_50` | behaviour | 50 decisions | share authenticated and policy-clean ≥ 0.98 | 0.75 |
| `control_execution` | control | 1 control instance | state is EVIDENCED | 0.75 |

Observation counts on the example stream run from 1,000 down to 8. That range is
why the estimates carry intervals: the same method gives a width of 0.05 on a
thousand observations and 0.40 on eight.

## Two thresholds

They are different objects and it is easy to conflate them.

`threshold` applies to the statistic and decides whether one window passes. For
fairness that is 0.80, the four-fifths ratio.

`theta_threshold` applies to the posterior and decides the band. It is the share
of windows that must pass. Fairness uses 0.90, the others 0.75.

Both are choices. Nothing in the code derives either.

## Parameters

Anything the measurement function needs beyond the criterion goes in
`parameters`, so it is not written in both the contract and the code:

```json
"measurement_function": "confidence >= min_confidence and latency_ms <= max_latency_ms and not error",
"parameters": {"min_confidence": 0.70, "max_latency_ms": 300}
```

`measures.py` reads them with `contract.param("min_confidence")`, which raises if
the parameter is not declared.

## Adding a measure

1. Write the contract, including the estimand and the limitations.
2. Add a function to `measures.py` taking `(records, contract, **context)` and
   returning `Observation` objects; register it in `MEASURE_FUNCTIONS`.
3. Add the measure to `escalation_probability`, `consequence` and
   `dependence.order` in `risk_scenario.yaml`, and extend the dependence matrix.

No engine change is needed. See [`../exercises.md`](../exercises.md).
