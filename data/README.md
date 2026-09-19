# `data/`

Committed inputs and generated artifacts.

## Committed inputs

| File | What it is |
|---|---|
| `control_evidence.json` | The control register: one row per control instance, its accountable role, its state and its last evidence date. This is control evidence, and the library will not let it update a behavioural measure. |
| `reference_distribution.json` | Feature means and standard deviations from training. Drift is measured against these, so they belong to training time rather than to a run. **A run never writes this file** — `write_reference_distribution` refuses to. |

The other committed inputs are [`../contracts/`](../contracts) and
[`../risk_scenario.yaml`](../risk_scenario.yaml).

## Generated artifacts

Gitignored. Each is written by one notebook and read by the next; each is
validated against a schema in [`../schemas/`](../schemas) before it is written.

| File | Written by | Read by |
|---|---|---|
| `telemetry.jsonl` | `01_telemetry`, or 2 or 3 when missing | Notebooks 2 and 3 |
| `reference_distribution.generated.json` | `01_telemetry`, or 2 or 3 when missing | Notebooks 2 and 3 |
| `posterior_state.json` | `02_bayesian_scoring`, or 3 when missing | Notebook 3 |
| `control_state.json` | `02_bayesian_scoring` | — |
| `risk_report.json` | `03_monte_carlo` | — |
| `decision_contracts.json` | `03_monte_carlo` | a pipeline |

Running the notebooks in order is the quickest path, not a requirement. Notebooks
2 and 3 regenerate any of the above they are missing, from the same seeded
generator and the same observations, so each can be run on its own.

Notebooks 2 and 3 use the generated reference distribution when it exists, so they
measure drift against the same reference the telemetry came from, and fall back to
the committed one otherwise. That is what lets them run without Notebook 1 while
keeping a local run self-consistent.

`tests/fixtures/telemetry.jsonl` is a committed copy of the stream Notebook 1
generates. Tests read it rather than regenerating so they do not depend on the
installed scikit-learn version.
