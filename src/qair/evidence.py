"""Evidence types, observations and the control register.

Two evidence types reach the estimator:

``system_behavior``
    Pass/fail outcomes on measurement windows, computed from telemetry.

``control``
    Records that a required control was executed within its interval.

They estimate different quantities, so a measure declares which type may update
it and :func:`check_evidence_type` rejects the other.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Sequence

from qair.contracts import ContractError, MeasurementContract
from qair.timeutil import parse_utc, to_utc

__all__ = [
    "CONTROL_STATES",
    "ControlRecord",
    "ControlRegister",
    "EvidenceType",
    "Observation",
    "check_evidence_type",
    "divergences",
    "typed_observations",
]

EvidenceType = Literal["system_behavior", "control"]

CONTROL_STATES = ("EVIDENCED", "ATTESTED_ONLY", "STALE", "NO_EVIDENCE")


@dataclass(frozen=True)
class Observation:
    """One observed window and its outcome.

    ``observed_at`` is None when the evidence carries no usable date. Such an
    observation still counts toward the volume requirement but cannot support a
    freshness claim.
    """

    measure_id: str
    evidence_type: str
    passed: bool
    observed_at: datetime | None = None
    statistic: float | None = None
    window_index: int | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        if self.evidence_type not in ("system_behavior", "control"):
            raise ContractError(
                f"{self.measure_id}: unknown evidence_type {self.evidence_type!r}"
            )
        if self.observed_at is not None:
            object.__setattr__(self, "observed_at", to_utc(self.observed_at))


@dataclass(frozen=True)
class ControlRecord:
    """One control instance in the register.

    ``covers_measure`` names the measure this control is meant to keep inside
    tolerance, when there is one. It is used to compare an attested control state
    with a measured system state; neither updates the other.
    """

    control_id: str
    description: str
    owner: str
    state: str
    last_evidence: str | None = None
    covers_measure: str | None = None

    def __post_init__(self) -> None:
        if self.state not in CONTROL_STATES:
            raise ContractError(
                f"{self.control_id}: state {self.state!r} not in {CONTROL_STATES}"
            )

    @property
    def evidenced(self) -> bool:
        """The estimand is "evidenced within its declared interval".

        ATTESTED_ONLY and STALE both fail it: the first is unverified, the second
        predates the interval.
        """
        return self.state == "EVIDENCED"

    @property
    def evidence_date(self) -> datetime | None:
        return parse_utc(self.last_evidence) if self.last_evidence else None


@dataclass
class ControlRegister:
    """The control evidence register: one row per control instance."""

    records: list[ControlRecord] = field(default_factory=list)
    generated_at: str = ""
    register_refreshed_at: str | None = None

    @classmethod
    def from_file(cls, path: Path | str) -> "ControlRegister":
        raw = json.loads(Path(path).read_text())
        return cls(
            records=[ControlRecord(**r) for r in raw["controls"]],
            generated_at=raw.get("generated_at", ""),
            register_refreshed_at=raw.get("register_refreshed_at"),
        )

    def aged(self, days: int) -> "ControlRegister":
        """A copy with every evidence date moved ``days`` further into the past."""
        shifted = []
        for r in self.records:
            last = r.last_evidence
            if last:
                last = (datetime.fromisoformat(last) - timedelta(days=days)).date().isoformat()
            shifted.append(
                ControlRecord(r.control_id, r.description, r.owner, r.state,
                              last, r.covers_measure)
            )
        refreshed = self.register_refreshed_at
        if refreshed:
            refreshed = (datetime.fromisoformat(refreshed) - timedelta(days=days)).isoformat()
        return ControlRegister(shifted, self.generated_at, refreshed)

    def observations(self, contract: MeasurementContract) -> list[Observation]:
        """One control-evidence observation per control instance.

        A control with no evidence date produces an observation with no date. It
        counts as a failure of the criterion and contributes nothing to freshness.
        """
        if contract.evidence_type != "control":
            raise ContractError(
                f"The control register cannot produce observations for "
                f"{contract.measure_id!r}, which declares evidence_type "
                f"{contract.evidence_type!r}"
            )
        return [
            Observation(
                measure_id=contract.measure_id,
                evidence_type="control",
                passed=r.evidenced,
                observed_at=r.evidence_date,
                window_index=i,
                detail=f"{r.control_id}: {r.state}",
            )
            for i, r in enumerate(self.records)
        ]

    def counts(self) -> dict[str, int]:
        return {s: sum(1 for r in self.records if r.state == s) for s in CONTROL_STATES}

    def to_document(
        self,
        divergence_rows: Sequence[dict[str, Any]] = (),
        reported_at: str = "",
    ) -> dict[str, Any]:
        """The ``control_state.json`` document: a register, not an estimate."""
        return {
            "schema_version": "1.0",
            "document": "control_state",
            "generated_at": self.generated_at,
            "reported_at": reported_at,
            "register_refreshed_at": self.register_refreshed_at,
            "controls": [
                {
                    "control_id": r.control_id,
                    "description": r.description,
                    "owner": r.owner,
                    "state": r.state,
                    "last_evidence": r.last_evidence,
                    "covers_measure": r.covers_measure,
                }
                for r in self.records
            ],
            "counts": self.counts(),
            "divergences": list(divergence_rows),
        }


def divergences(register: ControlRegister, states: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Controls recorded as run where the measure they cover reads WEAK.

    Both records can be accurate at once: the control owner attests to a process
    and usually has no view of the measurement. The pair is reported, not merged.
    """
    rows: list[dict[str, Any]] = []
    for r in register.records:
        if not r.covers_measure or r.covers_measure not in states:
            continue
        if r.state not in ("EVIDENCED", "ATTESTED_ONLY"):
            continue
        st = states[r.covers_measure]
        if st.band != "WEAK":
            continue
        rows.append(
            {
                "control_id": r.control_id,
                "control_state": r.state,
                "measure_id": r.covers_measure,
                "measured_band": st.band,
                "findings": [
                    {
                        "finding": (
                            f"{r.covers_measure} is WEAK: {st.n_failed} of "
                            f"{st.n_observations} windows failed the criterion."
                        ),
                        "owner": "model owner",
                    },
                    {
                        "finding": (
                            f"Control {r.control_id!r} is recorded as {r.state} and "
                            f"has not been compared against the measurement."
                        ),
                        "owner": r.owner,
                    },
                ],
            }
        )
    return rows


def check_evidence_type(contract: MeasurementContract, observation: Observation) -> None:
    """Raise ContractError when an observation's evidence type does not match."""
    if observation.measure_id != contract.measure_id:
        raise ContractError(
            f"Observation is for {observation.measure_id!r}, contract is for "
            f"{contract.measure_id!r}"
        )
    if observation.evidence_type != contract.evidence_type:
        raise ContractError(
            f"{observation.evidence_type!r} evidence cannot update "
            f"{contract.measure_id!r}, which declares evidence_type "
            f"{contract.evidence_type!r}. Control evidence records whether a "
            f"process ran; behavioural evidence records whether outputs met a "
            f"criterion."
        )


def typed_observations(
    contract: MeasurementContract, observations: Iterable[Observation]
) -> list[Observation]:
    checked = list(observations)
    for o in checked:
        check_evidence_type(contract, o)
    return checked
