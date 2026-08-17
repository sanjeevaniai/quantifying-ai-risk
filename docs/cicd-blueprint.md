# CI/CD Integration Blueprint

Where governance scoring sits in a pipeline. Three places, three different jobs. Short on purpose.

## The integration contract

Everything below consumes one file and one number:

- **`scorecard.json`** — per pillar: posterior, credible interval, threshold, band, pass or fail. Written by the scoring job (Notebooks 2 and 3 produce the reference implementation at `notebooks/outputs/scorecard.json`).
- **Exit code** — `0` if every pillar passes its threshold, `1` otherwise.

Governance scoring usually fails to reach a pipeline because nobody ever emitted a machine-readable result. The contract is the fix. What a pipeline does with the result is a policy decision, recorded where policy decisions are recorded — see "Where Thresholds Come From" in the course.

## 1. Pre-merge gate

Runs on the pull request. Scores the candidate model against held-out data and blocks the merge if a pillar is below threshold.

- **Character:** fast, blocking, cheap.
- **Limit:** can only use pillars computable without production traffic — Performance and Data quality on held-out data, Security configuration checks, Process (are the required sign-offs present?). Drift and Fairness need production windows and do not belong here.

```yaml
# e.g. GitHub Actions
- name: Governance gate
  run: |
    python score.py --mode pre-merge --candidate model/ --data holdout/
    # score.py writes scorecard.json and exits 0/1; a non-zero exit fails the job
- uses: actions/upload-artifact@v4
  with: { name: scorecard, path: scorecard.json }
```

## 2. Post-deploy monitor

Runs continuously on live telemetry. Watches for drift and degradation; alerts, and can trigger a rollback.

- **Character:** continuous, non-blocking. Nothing about a running system should hang on a scoring job.
- **Wiring:** the scoring job reads a window from the event sink on a schedule (e.g. every 15 minutes), updates the windowed pillars, and pushes `scorecard.json` to the monitoring stack. Alert rules read the file — for example, alert when any pillar's band leaves STRONG, page when a pillar fails.

## 3. Scheduled rescore

Weekly or monthly, on the full window. Recomputes the windowed pillars, refreshes attestations, writes the scorecard.

- **Character:** slow, thorough. This is the run that produces your audit record.
- **Wiring:** a cron job runs the full pipeline (the three notebooks are the reference), commits `scorecard.json` with a timestamp to an evidence store, and files the divergence report (attested versus measured) with the control owners.

## Thresholds fire; people decide

A threshold crossing produces an event; what fires — a blocked merge, a rollback, a retraining ticket — is set by a named person, recorded with the date, the reasoning, and the sign-off. The pipeline enforces the decision; it does not make it.
