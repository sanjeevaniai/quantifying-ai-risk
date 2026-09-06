# Where the decision contract fits in a pipeline

Three jobs with different constraints, all consuming `data/decision_contracts.json`
and the exit code derived from it.

```
band                   decision   gate
STRONG                 APPROVE    pass
ADEQUATE               REVIEW     pass, flagged
WEAK                   BLOCK      fail
INSUFFICIENT_EVIDENCE  HOLD       fail
```

`HOLD` blocks. A measure that cannot be reported should not pass a gate quietly;
in the `missing_documentation` scenario the loss figure improves while the gate
fails.

## What each job can compute

The constraint is data, not speed. A measure needs a window of production traffic
or it does not exist yet.

| Measure | Pre-merge | Post-deploy | Scheduled |
|---|---|---|---|
| `performance_per_decision` | yes, on held-out data | yes | yes |
| `data_quality_50` | yes, on held-out data | yes | yes |
| `drift_distance_50` | no | yes | yes |
| `fairness_parity_75` | no | yes | yes |
| `security_authz_50` | no | yes | yes |
| `control_execution` | register only | register only | yes, refreshed |

## 1. Pre-merge gate

Runs on the pull request against held-out data, and blocks the merge on a failure.
Fast and blocking.

It can only use measures computable without production traffic. Drift and fairness
need a window of live decisions and do not belong here — a pre-merge gate that
claims to check production fairness is checking something else.

`score.py` is yours to write; this repository ships the library, not the job:

```python
import json
import sys
from pathlib import Path

from qair.contracts import load_contracts
from qair.decisions import build_decision_contracts, exit_code_from
from qair.inference import estimate
from qair.risk import load_scenario
import measures

PRE_MERGE = ("performance_per_decision", "data_quality_50")

contracts = load_contracts()
scenario = load_scenario()
states = {
    mid: estimate(c, measures.window_observations(c, holdout_records), reported_at)
    for mid, c in contracts.items()
    if mid in PRE_MERGE
}
doc = build_decision_contracts(states, {m: contracts[m] for m in states}, scenario,
                               model_id, model_version, policy_version)
Path("data/decision_contracts.json").write_text(json.dumps(doc, indent=2))
sys.exit(exit_code_from(doc))
```

```yaml
- name: Governance gate
  run: python score.py --candidate model/ --data holdout/
- uses: actions/upload-artifact@v4
  if: always()
  with:
    name: decision-contracts
    path: data/decision_contracts.json
```

## 2. Post-deploy monitor

Runs on live telemetry on a schedule. Non-blocking: a running system should not
depend on a scoring job finishing.

It can compute every behavioural measure, because production traffic exists. It
cannot refresh control evidence, which arrives from people on its own cadence, so
`control_execution` here reflects whatever the register last said.

Alert on `INSUFFICIENT_EVIDENCE` separately from a failing measure. They are
different conditions: one means the system is outside tolerance, the other means
you have stopped being able to tell.

## 3. Scheduled rescore

Weekly or monthly over the full window. Slow and thorough, and the run that
produces the record an auditor asks for.

It is the only job that can refresh control evidence and recompute measures needing
a large population. It writes all four documents to an evidence store with a
timestamp, and files the divergences from `control_state.json` with the control
owners.

## Thresholds

A threshold crossing produces an event. What it should trigger — a blocked merge,
a rollback, a retraining ticket — is decided in advance and recorded against the
contract with the value, the date, the reasoning and the accountable role.

The pipeline enforces that decision; it does not derive it.
