# Architecture

```
telemetry → measurement → evidence → estimation → simulation → decision
```

## Stages

| Stage | Module | What it does |
|---|---|---|
| OBSERVE | `qair.telemetry` | Emit, validate and store decision records |
| MEASURE | `measures.py`, `qair.contracts` | Compute window statistics against declared criteria |
| MEASURE | `qair.evidence` | Type observations and load the control register |
| INFER | `qair.inference` | One Beta-Binomial posterior per measure |
| SIMULATE | `qair.risk` | Monte Carlo loss model and counterfactual scenarios |
| DECIDE | `qair.decisions` | Decision contracts and the derived exit code |

`measures.py` sits outside the package on purpose: it is the only file that knows
anything about the worked example. `qair` is generic.

## The notebooks

Each reads what the previous one wrote, so any stage can be re-run alone and a
stage can be replaced as long as it reads and writes the same schema.

| Notebook | Reads | Writes |
|---|---|---|
| `01_telemetry` | `contracts/`, `data/reference_distribution.json` | `data/telemetry.jsonl` |
| `02_bayesian_scoring` | `data/telemetry.jsonl`, `contracts/`, `data/control_evidence.json` | `data/posterior_state.json`, `data/control_state.json` |
| `03_monte_carlo` | `data/posterior_state.json`, `risk_scenario.yaml` | `data/risk_report.json`, `data/decision_contracts.json` |

## Where values are declared

Nothing in `src/qair` hard-codes a window length, a threshold or a cost.

| Value | Declared in |
|---|---|
| Window length, criterion, thresholds, prior, sufficiency, owner, limitations | `contracts/<measure>.json` |
| Measurement constants the statistic reads | `contracts/<measure>.json` → `parameters` |
| Monthly volume, escalation, cost, dependence, seeds | `risk_scenario.yaml` |
| The window statistic itself | `measures.py` |

Exposure per measure is derived from the monthly volume and the window length, so
window lengths appear in one place.

## Number of measures

The example has six. The engine has no fixed count: `load_contracts` reads every
file in the directory, the schemas constrain the shape of a measure entry rather
than the set of ids, and the dependence matrix is validated against whatever
`dependence.order` names.

Adding a measure means a contract file, a function registered in
`MEASURE_FUNCTIONS`, and an entry in `risk_scenario.yaml`.

## Generated documents

Each is validated against a schema in `schemas/` before it is written.

| Document | Contents |
|---|---|
| `telemetry.jsonl` | One decision record per line |
| `posterior_state.json` | Per measure: estimand, prior, posterior, counts, interval, band, sufficiency |
| `control_state.json` | Control register rows, state counts, divergences. No estimates |
| `risk_report.json` | Simulation results and the assumptions behind them |
| `decision_contracts.json` | Per measure: estimate, threshold in force, decision, and the derived exit code |
