"""qair — a worked telemetry-to-risk pipeline.

OBSERVE -> MEASURE -> INFER -> SIMULATE -> DECIDE

    telemetry   emit and validate decision records
    contracts   load the declared definition of each measure
    evidence    typed observations and the control register
    inference   per-measure Bayesian estimation
    risk        Monte Carlo loss simulation
    decisions   decision contracts and the exit code

Window lengths, criteria and thresholds come from contracts/. Exposure and
monetary parameters come from risk_scenario.yaml.
"""

__version__ = "0.2.0"
