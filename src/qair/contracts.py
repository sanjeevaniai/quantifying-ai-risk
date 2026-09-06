"""Measurement contracts: the declared definition of each measure."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

__all__ = [
    "ContractError",
    "MeasurementContract",
    "contracts_dir",
    "load_contract",
    "load_contracts",
]

_REQUIRED = (
    "measure_id",
    "construct",
    "estimand",
    "evidence_type",
    "observable_fields",
    "window",
    "measurement_function",
    "operator",
    "threshold",
    "theta_threshold",
    "prior",
    "sufficiency",
    "owner",
    "limitations",
)

EVIDENCE_TYPES = ("system_behavior", "control")


class ContractError(Exception):
    """Raised when an operation would violate a measurement contract."""


@dataclass(frozen=True)
class MeasurementContract:
    """One declared measure, loaded from a file in ``contracts/``."""

    measure_id: str
    construct: str
    estimand: str
    evidence_type: str
    observable_fields: tuple[str, ...]
    window_length: int
    window_unit: str
    measurement_function: str
    operator: str
    threshold: float
    theta_threshold: float
    prior_alpha: float
    prior_beta: float
    prior_mode: str
    min_observations: int
    max_age_days: int
    owner: str
    limitations: tuple[str, ...] = ()
    parameters: Mapping[str, Any] = field(default_factory=dict)

    @property
    def window(self) -> str:
        unit = self.window_unit
        if self.window_length == 1 and unit.endswith("s"):
            unit = unit[:-1]
        return f"{self.window_length} {unit}"

    @property
    def prior(self) -> tuple[float, float]:
        return (self.prior_alpha, self.prior_beta)

    def param(self, name: str) -> Any:
        """Read a measurement parameter declared in the contract."""
        if name not in self.parameters:
            raise ContractError(
                f"{self.measure_id}: no parameter {name!r} in the contract. "
                f"Declared: {sorted(self.parameters)}"
            )
        return self.parameters[name]

    def exposure_windows(self, monthly_decisions: int, control_instances: int) -> int:
        """Opportunities to breach this criterion in one month."""
        if self.window_unit == "control_instances":
            return int(control_instances)
        return int(monthly_decisions // self.window_length)

    def to_dict(self) -> dict[str, Any]:
        return {
            "measure_id": self.measure_id,
            "construct": self.construct,
            "estimand": self.estimand,
            "evidence_type": self.evidence_type,
            "observable_fields": list(self.observable_fields),
            "window": self.window,
            "measurement_function": self.measurement_function,
            "operator": self.operator,
            "threshold": self.threshold,
            "theta_threshold": self.theta_threshold,
            "parameters": dict(self.parameters),
            "owner": self.owner,
            "limitations": list(self.limitations),
        }


def contracts_dir(start: Path | str | None = None) -> Path:
    here = Path(start) if start is not None else Path(__file__).resolve()
    for candidate in [here, *here.parents]:
        target = candidate / "contracts"
        if target.is_dir() and any(target.glob("*.json")):
            return target
    raise FileNotFoundError("No contracts/ directory found above " + str(here))


def _from_mapping(raw: Mapping[str, Any], source: str) -> MeasurementContract:
    missing = [f for f in _REQUIRED if f not in raw]
    if missing:
        raise ContractError(f"{source}: missing field(s) {', '.join(missing)}")
    if raw["evidence_type"] not in EVIDENCE_TYPES:
        raise ContractError(
            f"{source}: evidence_type must be one of {EVIDENCE_TYPES}, "
            f"got {raw['evidence_type']!r}"
        )
    if not str(raw["estimand"]).strip():
        raise ContractError(f"{source}: estimand is empty")

    window, prior, suff = raw["window"], raw["prior"], raw["sufficiency"]
    return MeasurementContract(
        measure_id=raw["measure_id"],
        construct=raw["construct"],
        estimand=raw["estimand"],
        evidence_type=raw["evidence_type"],
        observable_fields=tuple(raw["observable_fields"]),
        window_length=int(window["length"]),
        window_unit=str(window["unit"]),
        measurement_function=raw["measurement_function"],
        operator=raw["operator"],
        threshold=float(raw["threshold"]),
        theta_threshold=float(raw["theta_threshold"]),
        prior_alpha=float(prior["alpha"]),
        prior_beta=float(prior["beta"]),
        prior_mode=str(prior["mode"]),
        min_observations=int(suff["min_observations"]),
        max_age_days=int(suff["max_age_days"]),
        owner=raw["owner"],
        limitations=tuple(raw["limitations"]),
        parameters=dict(raw.get("parameters", {})),
    )


def load_contract(measure_id: str, directory: Path | str | None = None) -> MeasurementContract:
    d = Path(directory) if directory is not None else contracts_dir()
    path = d / f"{measure_id}.json"
    if not path.exists():
        raise ContractError(f"No contract for {measure_id!r} at {path}")
    return _from_mapping(json.loads(path.read_text()), str(path))


def load_contracts(directory: Path | str | None = None) -> dict[str, MeasurementContract]:
    """Load every contract in the directory, keyed by measure id.

    Any number of measures is supported. The worked example ships six; adding a
    seventh means adding a file here and an entry in risk_scenario.yaml.
    """
    d = Path(directory) if directory is not None else contracts_dir()
    loaded: dict[str, MeasurementContract] = {}
    for path in sorted(d.glob("*.json")):
        contract = _from_mapping(json.loads(path.read_text()), str(path))
        if contract.measure_id != path.stem:
            raise ContractError(
                f"{path}: measure_id {contract.measure_id!r} does not match the filename"
            )
        loaded[contract.measure_id] = contract
    if not loaded:
        raise ContractError(f"No contracts found in {d}")
    return loaded
