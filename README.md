# Quantifying AI Risk

A worked Python example that turns synthetic AI decision telemetry into
measurement contracts, Bayesian estimates, simulated risk, and an operational
decision.

The data and monetary assumptions are illustrative. The engineering patterns are
intended to be adapted.

```
Fork → install → run notebooks → change a contract → rerun
```

## Install

```bash
git clone https://github.com/sanjeevaniai/quantifying-ai-risk.git
cd quantifying-ai-risk
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python setup_check.py
jupyter notebook notebooks/01_telemetry.ipynb
```

Python 3.10 or newer. There is no build step; the notebooks put the repository
root and `src/` on `sys.path` themselves.

On Colab, open a notebook with a badge below and run the first cell — it clones
the repository and installs the requirements. Run all three in the same session,
since each reads what the previous one wrote.

| | Notebook | Colab |
|---|---|---|
| 1 | [`01_telemetry.ipynb`](notebooks/01_telemetry.ipynb) | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/sanjeevaniai/quantifying-ai-risk/blob/main/notebooks/01_telemetry.ipynb) |
| 2 | [`02_bayesian_scoring.ipynb`](notebooks/02_bayesian_scoring.ipynb) | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/sanjeevaniai/quantifying-ai-risk/blob/main/notebooks/02_bayesian_scoring.ipynb) |
| 3 | [`03_monte_carlo.ipynb`](notebooks/03_monte_carlo.ipynb) | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/sanjeevaniai/quantifying-ai-risk/blob/main/notebooks/03_monte_carlo.ipynb) |

## The three notebooks

**1. Telemetry and measurement.** Generate 1,000 decision records from a small
scikit-learn classifier, with drift injected at record 600. Validate them, then
compute each measure against the criterion in its contract.
Writes `data/telemetry.jsonl`.

**2. Bayesian estimation.** Turn window outcomes into one Beta-Binomial posterior
per measure, with a credible interval and a band. Check evidence sufficiency, test
the prior and the thresholds, and compare the control register against the
measured state.
Writes `data/posterior_state.json` and `data/control_state.json`.

**3. Risk simulation and decisions.** Sample from the posteriors, draw breaches
and costs, run counterfactual scenarios, and emit a decision contract per measure
with a process exit code.
Writes `data/risk_report.json` and `data/decision_contracts.json`.

`data/README.md` lists every file, which notebook writes it, and which reads it.

## What is illustrative

- **The telemetry is synthetic.** The applicants, the drift timing, the caller mix
  and the failure rates are generated. The record shape is real.
- **The monetary assumptions are illustrative.** `risk_scenario.yaml` declares
  `mode: illustrative`, meaning nothing in it is calibrated from incident history.
  Escalation probabilities and monthly volume together set the size of every
  dollar figure, and neither is measured. Notebook 3 shows how much moves when
  they do.
- **The engineering patterns are the transferable part**: contracts that declare a
  measure before it is computed, evidence typing, per-measure estimation with
  intervals, a sufficiency state that blocks rather than silently passing, and
  machine-readable outputs.

It is not a compliance tool, a trust score, or a calibrated loss model.

## Easiest things to change

| Change | Where | Effect |
|---|---|---|
| A threshold | `contracts/<measure>.json` → `theta_threshold` | Bands and the gate move; estimates do not |
| A criterion | `contracts/<measure>.json` → `operator`, `threshold`, `parameters` | Window outcomes change, so posteriors do |
| Cost or volume | `risk_scenario.yaml` | Every monetary figure moves |
| Stream length, drift point, seed | `qair.TelemetryConfig` in Notebook 1 | New telemetry |
| A window statistic | `measures.py` | How a measure is computed |

Adding a measure needs a contract file, a function in `measures.py`, and an entry
in `risk_scenario.yaml`. No engine code changes — see
[`exercises.md`](exercises.md).

## Adapting it to your own system

`measures.py` is the only file that knows anything about credit decisioning.
Replace it with functions over your own records, write a contract per measure, and
the rest of the pipeline works unchanged.

The parts most worth taking: the contract shape, the evidence-type check, and the
decision contract as an integration surface. See
[`docs/cicd-blueprint.md`](docs/cicd-blueprint.md) for where the last one fits in
a pipeline.

## Layout

```
contracts/          one JSON file per measure
risk_scenario.yaml  exposure and monetary parameters
measures.py         window statistics for this example
schemas/            JSON Schema for every generated document
src/qair/           telemetry, contracts, evidence, inference, risk, decisions
notebooks/          the three notebooks
data/               committed inputs and generated artifacts
tests/
docs/
```

Window lengths, criteria and thresholds live in `contracts/`. Exposure and money
live in `risk_scenario.yaml`. Neither is repeated in code.

## Tests

```bash
pytest
```

Covers the estimation invariants, evidence typing, sufficiency behaviour,
simulation properties, dependence-matrix validation, schema conformance, and
reference values the pipeline should reproduce from the committed fixture. CI runs
them on Python 3.10, 3.11 and 3.12 and executes all three notebooks.

## Reproducibility

Simulated statistics depend on the seed. The tail moves about 10% across seeds
even at 50,000 months; Notebook 3 measures and prints this, and it is the floor on
how precisely anything should be quoted.

Window outcomes depend on the model coefficients, which in principle can shift
between scikit-learn releases. In practice they have not: the pipeline produces
identical telemetry, posteriors and loss figures on Python 3.10 with
scikit-learn 1.7.2 / numpy 1.26 and on Python 3.11 with scikit-learn 1.9.0 /
numpy 2.4. The tests read `tests/fixtures/telemetry.jsonl` rather than
regenerating, so they do not rely on that continuing to hold.

## Docs

| | |
|---|---|
| [`architecture.md`](docs/architecture.md) | Stages, modules, and where each quantity is declared |
| [`measurement-contracts.md`](docs/measurement-contracts.md) | Contract fields and how to add a measure |
| [`evidence-model.md`](docs/evidence-model.md) | Behavioural and control evidence, and the divergence report |
| [`risk-model.md`](docs/risk-model.md) | The loss model, dependence, scenarios, stability |
| [`assumptions.md`](docs/assumptions.md) | Every assumption, what it affects, and how to replace it |
| [`limitations.md`](docs/limitations.md) | What this does not establish |
| [`cicd-blueprint.md`](docs/cicd-blueprint.md) | Where the decision contract fits in a pipeline |

## License

MIT. See [LICENSE](LICENSE). Course material by
[Suneeta Modekurty](https://www.linkedin.com/in/smodekurty).
