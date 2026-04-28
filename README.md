# Quantifying AI Risk

**Building a Telemetry-Driven Risk Scoring Engine for Production AI**

Companion repository for the O'Reilly Live Training Course taught by [Suneeta Modekurty](https://www.linkedin.com/in/suneetamodekurty).

---

## What you will build

Over three hours, you will build a complete pipeline that takes a production AI system from "we hope it's behaving" to "we can defend its behavior to a regulator, an executive, and a customer." The pipeline has three stages:

**Hour 1: Telemetry.** Instrument a production model so it emits six governance signals: decision, confidence, latency, drift, fairness, and operational health. Each signal is decision-bound, timestamped, and stored in a tamper-evident event sink.

**Hour 2: Bayesian inference.** Turn the telemetry stream into six independent posterior distributions, one per signal, each with its own credible interval. Skeptical priors. Severity-weighted likelihoods. Per-signal updates that preserve the evidence each regulatory framework actually asks for.

**Hour 3: Monte Carlo simulation.** Translate the six posteriors into a financial risk distribution. Compute expected loss, 95% Value at Risk, and 95% Tail Conditional Expectation. Run sensitivity analysis to find which signals drive catastrophic tail risk.

By the end, you have a working measurement-and-inference pipeline you can run against your own systems.

---

## Notebooks

Each notebook can run on either your local machine or in Google Colab. Click the Colab badge to open in your browser with no setup required.

| Hour | Notebook | Open in Colab |
|------|----------|---------------|
| Hour 1 | [`notebooks/01_telemetry.ipynb`](notebooks/01_telemetry.ipynb) | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/sanjeevaniai/quantifying-ai-risk/blob/main/notebooks/01_telemetry.ipynb) |
| Hour 2 | [`notebooks/02_bayesian_scoring.ipynb`](notebooks/02_bayesian_scoring.ipynb) | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/sanjeevaniai/quantifying-ai-risk/blob/main/notebooks/02_bayesian_scoring.ipynb) |
| Hour 3 | [`notebooks/03_monte_carlo.ipynb`](notebooks/03_monte_carlo.ipynb) | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/sanjeevaniai/quantifying-ai-risk/blob/main/notebooks/03_monte_carlo.ipynb) |

The notebooks are designed to run in order. Notebook 1 emits telemetry events that Notebook 2 reads. Notebook 2 produces posterior distributions that Notebook 3 samples from.

---

## Setup: Local

If you want to run the notebooks on your own machine:

```bash
git clone https://github.com/sanjeevaniai/quantifying-ai-risk.git
cd quantifying-ai-risk
python -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate            # Windows PowerShell
pip install -r requirements.txt
python setup_check.py
jupyter notebook notebooks/01_telemetry.ipynb
```

**Requirements:**
- Python 3.10 or newer
- Roughly 500 MB of disk space for dependencies
- A web browser for Jupyter

`setup_check.py` verifies your Python version and that every dependency imports cleanly. Run it before the course starts so any environment issues are resolved before Hour 1.

---

## Setup: Colab (no install required)

Click any of the **Open in Colab** badges above. Colab handles Python, dependencies, and Jupyter for you. The first cell of each notebook installs the few packages Colab does not have by default. Notebooks 2 and 3 read files written by earlier notebooks; on Colab you will need to either run all three notebooks in the same session or re-upload the intermediate files when you switch.

---

## Repository contents

```
quantifying-ai-risk/
├── README.md                     This file
├── LICENSE                       MIT
├── requirements.txt              Pinned Python dependencies
├── setup_check.py                Environment verification script
├── .gitignore                    Python and Jupyter conventions
├── notebooks/
│   ├── 01_telemetry.ipynb        Hour 1, instrumenting a model
│   ├── 02_bayesian_scoring.ipynb Hour 2, per-signal posteriors
│   └── 03_monte_carlo.ipynb      Hour 3, financial risk simulation
└── data/
    └── sample_telemetry/         Sample events for Notebook 1
```

---

## How to use this repo after the course

The methodology in this course is a starting point, not a finished product. Three suggested next steps:

1. **Run the three notebooks against one of your own systems.** Even a small one. Even with synthetic loss numbers at first. The exercise of going from zero to a working pipeline on real telemetry is what locks the methodology in.
2. **Extend the schema.** The six signals here are the minimum evidentiary foundation. Your industry may need more. Add them with the same per-signal posterior pattern.
3. **Calibrate the loss functions.** The loss functions in Notebook 3 are deliberately simple. Production calibration uses your own incident history and your own legal exposure. The shape of the model is right; the numbers are illustrative.

---

## Recommended reading

Books on the O'Reilly platform that pair well with this course. The first four extend the technical methods you build here. The last two extend the operational context for putting this into production.

- **[Think Bayes, 2nd Edition](https://learning.oreilly.com/library/view/think-bayes-2nd/9781492089452/)** by Allen B. Downey. The gentlest path into the Bayesian reasoning you used in Hour 2. Read this if the prior and posterior intuition still feels fuzzy.
- **[Python for Data Analysis, 3rd Edition](https://learning.oreilly.com/library/view/python-for-data/9781098104023/)** by Wes McKinney. The canonical reference for working with telemetry data at scale once your event volume outgrows the patterns in this course.
- **[Designing Machine Learning Systems](https://learning.oreilly.com/library/view/designing-machine-learning/9781098107956/)** by Chip Huyen. System-level thinking about ML in production. The complementary lens to what we built: where this course quantifies risk, that book maps the surface area where risk lives.
- **[Reliable Machine Learning](https://learning.oreilly.com/library/view/reliable-machine-learning/9781098106218/)** by Cathy Chen et al. Applies SRE discipline to ML systems. Pairs naturally with the operational health signal from Hour 1.
- **[Practical MLOps](https://learning.oreilly.com/library/view/practical-mlops/9781098103002/)** by Noah Gift and Alfredo Deza. The CI/CD and deployment context. Useful when you start wiring the methodology from this course into your own pipelines.

## Stay connected

**Newsletter:** A.I.N.S.T.E.I.N. on Substack. Long-form essays on AI governance, telemetry, and quantitative trust scoring.

**LinkedIn:** [linkedin.com/in/suneetamodekurty](https://www.linkedin.com/in/suneetamodekurty). Send a connection request and mention this course.

**Practice:** The methodology taught in this course is operationalized as METRIS, an AI Trust Posture Management platform built by SANJEEVANI AI. [sanjeevaniai.com](https://sanjeevaniai.com)

---

## License

MIT. See [LICENSE](LICENSE).

You are free to use this code in your own work, including commercial projects, with attribution. If you build something interesting on top of it, I would love to hear about it.

---

*This course is a one-time live event on O'Reilly's platform. The notebooks and methodology in this repository are the durable artifacts.*
