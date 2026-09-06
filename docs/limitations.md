# Limitations

## What the numbers are not

Each theta is the probability that a window of declared length meets a declared
criterion. It is not a probability that a system is safe or compliant, and it is
not comparable across organisations: two teams running this code would declare
different windows, criteria, thresholds, volumes and costs.

The monetary figures are the output of declared assumptions in
`risk_scenario.yaml`, which says `mode: illustrative`. Nothing in it is calibrated
from incident history.

The measurement informs a decision. It does not make one: which threshold to set,
and what a failure should trigger, are recorded against the contract by a person.

## What is not measured

- **Correctness** is absent from the performance measure, because labels arrive
  after the decision. Concept drift and degradation are detected late as a result.
- **Control effectiveness.** `control_execution` records whether a control ran,
  not whether it worked.
- **Caller volume** is computed by `measures.caller_volume_share` and no measure
  scores it, because volume is derived from `caller_id` over a window rather than
  recorded.
- **Input provenance and authorisation scope** are named in the security
  contract's limitations and are not in the record schema.

## Integrity

The `checksum` field is a SHA-256 over the record. It detects corruption and
accidental edits. It is not a signature: anyone holding a record can recompute it,
so it says nothing about who wrote the record or whether it was deliberately
rewritten. Real tamper evidence needs a signing key, which this example does not
have.

## Dependence

The Gaussian copula is applied correctly — the realised theta correlations match
the declared matrix — but in this configuration it changes the loss tail by far
less than the seed spread. The tail here is driven by single heavy cost draws
rather than by measures failing together. See [`risk-model.md`](risk-model.md).

## Reproducibility

Simulated statistics depend on the seed, with a TCE spread of about 10% at 50,000
months. That is measured on every run and is the precision floor.

Window outcomes depend on model coefficients, which could shift between
scikit-learn releases. Across 1.7.2 and 1.9.0 they did not: every decision,
window outcome and loss figure was identical. The tests read a committed fixture
so they do not depend on that.

## Scale

Everything runs in memory over 1,000 records. Real volumes need a durable
append-only store, windowed queries against it, and incremental updates. The
Beta-Binomial update is sequential, so the statistics carry over; the I/O does not.

## The example data

The fairness disparity is injected by the generator. No conclusion about credit
decisioning follows from it.
