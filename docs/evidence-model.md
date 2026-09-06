# Evidence model

Two evidence types reach the estimator, and a measure declares which one may
update it.

**`system_behavior`** — pass/fail outcomes on measurement windows, computed from
telemetry. Answers whether outputs met a criterion.

**`control`** — records that a required control was executed within its interval.
Answers whether a process ran.

They estimate different things, so passing the wrong type to a measure raises
`ContractError`. The check runs in both directions: telemetry cannot update
`control_execution` either.

`control_execution` is a measure whose evidence happens to be the control
register, so that pairing is allowed.

## Control states

| State | Meaning | Passes the criterion |
|---|---|---|
| `EVIDENCED` | A machine-readable record exists | yes |
| `ATTESTED_ONLY` | Someone recorded that it happened; nothing verifies it | no |
| `STALE` | The last evidence predates the required interval | no |
| `NO_EVIDENCE` | No record | no |

`ATTESTED_ONLY` is not an accusation. The control owner is attesting that a
process took place, which is a different claim from the measurement.

## Missing evidence dates

A control with no `last_evidence` produces an observation with no timestamp. It
counts toward the volume requirement and fails the criterion, but contributes
nothing to freshness. No substitute timestamp is invented.

If no observation carries a date, freshness cannot be established and the measure
returns `INSUFFICIENT_EVIDENCE`.

## Two documents

`posterior_state.json` holds the estimate for `control_execution`: prior,
posterior, interval, band.

`control_state.json` holds the register: one row per control instance, the state
counts, and any divergences. It carries no alpha, beta, mean or band, because it
is a record rather than an estimate.

## Divergences

`qair.evidence.divergences` reports controls recorded as run whose covered
measure reads WEAK.

Both records can be accurate. The control owner attests that a review happened
and usually has no view of the parity measurements. The result is two findings
with two owners: the measure is outside tolerance, and the control has never been
compared against it.

`covers_measure` in the register names the link. It is a field of this example,
not something derivable from the data.

## Sufficiency

Declared per measure. Below `min_observations`, or with evidence older than
`max_age_days`, the measure returns `INSUFFICIENT_EVIDENCE` with no mean and no
interval — not just no band.

This is what catches a monitoring gap. A scoring job keeps producing output after
telemetry stops arriving; the number stays stable while the thing it estimates is
no longer being estimated. `INSUFFICIENT_EVIDENCE` maps to `HOLD`, which blocks
the gate, so the pipeline fails rather than passing on stale evidence.
