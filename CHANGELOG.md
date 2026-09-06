# Changelog

## 0.2.0

- Measures are data-driven: contract loading, schemas, generated documents and
  tests take any number of measures rather than a fixed six.
- Measurement constants (confidence and latency limits, drift scale, fairness
  reference group and smoothing) moved into contract `parameters`, so each value
  is written down once.
- The record integrity field is a `checksum`, not a signature, and
  `validate_record` verifies it.
- Missing control-evidence dates are no longer given a substitute timestamp. A
  measure with no dated evidence returns `INSUFFICIENT_EVIDENCE`.
- Timestamps are normalised rather than relabelled, so offset-aware inputs keep
  their meaning.
- The dependence matrix is validated on load: square, matching the declared
  order, symmetric, unit diagonal, entries in [-1, 1], positive definite.
- JSON Schema uses `$defs` for the repeated measure entry, accepts any configured
  measure id, and is checked with `jsonschema.FormatChecker()` so declared
  formats are enforced.
- Scenario analysis is named as counterfactual (`apply_counterfactual`,
  `counterfactual_scenarios` in the risk report) to keep it distinct from
  evidence ingestion.
- Notebook 1 writes `data/reference_distribution.generated.json` rather than
  overwriting the committed `data/reference_distribution.json`. Notebooks 2 and 3
  use the generated file when present and fall back to the committed one, so a
  run is self-consistent without modifying a tracked file.
- Verified on Python 3.10 (scikit-learn 1.7.2, numpy 1.26) and Python 3.11
  (scikit-learn 1.9.0, numpy 2.4): identical telemetry, posteriors and loss
  figures on both.

## 0.1.0

First public version: telemetry generation, measurement contracts, per-measure
Bayesian estimation, Monte Carlo risk simulation and decision contracts.
