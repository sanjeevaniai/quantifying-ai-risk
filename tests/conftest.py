"""Shared fixtures.

Everything is built from tests/fixtures/telemetry.jsonl, a committed copy of the
stream Notebook 1 generates. Using a fixture rather than regenerating keeps the
tests independent of the installed scikit-learn version, which sets the model
coefficients.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from qair.contracts import load_contracts
from qair.evidence import ControlRegister
from qair.inference import estimate
from qair.risk import load_scenario, seed_stability, simulate, tail_attribution
from qair.telemetry import read_jsonl, reference_distribution

import measures

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def records() -> list[dict]:
    return read_jsonl(ROOT / "tests" / "fixtures" / "telemetry.jsonl")


@pytest.fixture(scope="session")
def contracts():
    return load_contracts(ROOT / "contracts")


@pytest.fixture(scope="session")
def scenario():
    return load_scenario(ROOT / "risk_scenario.yaml")


@pytest.fixture(scope="session")
def register() -> ControlRegister:
    return ControlRegister.from_file(ROOT / "data" / "control_evidence.json")


@pytest.fixture(scope="session")
def reference():
    return reference_distribution(ROOT / "data" / "reference_distribution.json")


@pytest.fixture(scope="session")
def reported_at(scenario) -> datetime:
    return datetime.fromisoformat(scenario.reported_at)


@pytest.fixture(scope="session")
def observations(contracts, records, register, reference):
    ref_means, ref_stds = reference
    return {
        mid: (register.observations(c) if c.evidence_type == "control"
              else measures.window_observations(c, records,
                                                ref_means=ref_means, ref_stds=ref_stds))
        for mid, c in contracts.items()
    }


@pytest.fixture(scope="session")
def states(contracts, observations, reported_at):
    return {mid: estimate(contracts[mid], observations[mid], reported_at) for mid in contracts}


@pytest.fixture(scope="session")
def baseline(states, contracts, scenario):
    return simulate(states, contracts, scenario)


@pytest.fixture(scope="session")
def stability(states, contracts, scenario):
    return seed_stability(states, contracts, scenario)


@pytest.fixture(scope="session")
def attribution(states, contracts, scenario, baseline):
    return tail_attribution(states, contracts, scenario, baseline=baseline)


@pytest.fixture(scope="session")
def scenario_runs(states, contracts, scenario, register, reported_at):
    from qair.risk import apply_counterfactual

    return {
        name: simulate(
            apply_counterfactual(name, states, scenario, contracts=contracts,
                                 control_register=register, reported_at=reported_at),
            contracts, scenario,
        )
        for name in scenario.scenarios
    }
