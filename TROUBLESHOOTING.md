# Troubleshooting

Run `python setup_check.py` first; it names the failing check.

**A package is missing, or the notebook cannot import `qair`.**
Usually the notebook kernel is a different interpreter from the one you installed
into. Check with `import sys; print(sys.executable)` in a cell, then register the
right environment:

```bash
python -m ipykernel install --user --name qair --display-name "Quantifying AI Risk"
```

and pick that kernel from the notebook's kernel menu.

**`FileNotFoundError: No telemetry at data/telemetry.jsonl`.**
Notebook 2 reads what Notebook 1 wrote. Run Notebook 1 first; it takes about a
minute. The same applies to Notebook 3 and `data/posterior_state.json`.

**Colab: Notebook 2 cannot find the file Notebook 1 wrote.**
Each Colab notebook gets its own machine. Run all three in the same session, or
download `data/telemetry.jsonl` and upload it into the next session at the same
path. After a runtime reset, re-run the first cell.

**`RuntimeError: Run this notebook from inside a clone of the repository.`**
The first cell looks upward for a directory containing both `contracts/` and
`risk_scenario.yaml`. Move the notebook back into `notebooks/`, or open it in
Colab with a badge from the README.

**`ContractError` in Notebook 2.**
Two cells raise one on purpose, to show that evidence types are checked. Anywhere
else, the message names the measure and the evidence type that did not match.

**A measure reports `INSUFFICIENT_EVIDENCE`.**
Expected in two places in the notebooks. Otherwise the message says whether it was
volume or freshness. Both limits are in the measure's contract, and freshness is
compared against `reported_at` in `risk_scenario.yaml`.

**Notebook 3 is slow.**
50,000 months across five scenarios plus a seed check. Ten to thirty seconds
locally. Pass `n=` to `simulate` to iterate faster, but do not quote a tail
statistic from a short run.

**My numbers differ from the README.**
Tail statistics move about 10% across seeds, so expected loss, VaR and TCE will
not match exactly. Posteriors, bands and the exit code should. See the
reproducibility note in the README.
