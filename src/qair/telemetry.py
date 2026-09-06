"""Decision records: emit, validate, read and write.

Two halves, and the boundary matters:

* ``generate_stream`` and everything it calls is **demo data generation**. The
  applicants, the drift timing, the caller mix and the failure rates are made up
  for the worked example. None of it is an assumption about production.
* ``emit_record``, ``validate_record``, ``write_jsonl`` and ``read_jsonl`` are the
  reusable half. The record shape is the part worth copying.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

from qair.timeutil import parse_utc

__all__ = [
    "RECORD_SCHEMA",
    "FEATURES",
    "RANGES",
    "CALLERS",
    "DEFAULT_SEED",
    "DRIFT_START",
    "STREAM_LENGTH",
    "TelemetryConfig",
    "checksum",
    "generate_stream",
    "train_reference_model",
    "gen_applicants",
    "emit_record",
    "validate_record",
    "write_jsonl",
    "read_jsonl",
    "reference_distribution",
    "reference_distribution_path",
    "COMMITTED_REFERENCE",
    "GENERATED_REFERENCE",
    "newest_capture",
]

#: The committed reference distribution. Tracked, and never written by a run.
COMMITTED_REFERENCE = "reference_distribution.json"

#: Written by Notebook 1 when it retrains. Gitignored.
GENERATED_REFERENCE = "reference_distribution.generated.json"

DEFAULT_SEED = 42
DRIFT_START = 600
STREAM_LENGTH = 1000

FEATURES = (
    "log_income",
    "debt_to_income",
    "credit_history_len",
    "recent_defaults",
    "log_loan_amount",
)

RANGES: dict[str, tuple[float, float]] = {
    "log_income": (8.0, 14.5),
    "debt_to_income": (0.0, 1.5),
    "credit_history_len": (0.0, 40.0),
    "recent_defaults": (0.0, 10.0),
    "log_loan_amount": (7.0, 13.5),
}

CALLERS = ("web_portal", "branch_app", "partner_api", "svc_d")
_CALLER_SHARE = (0.55, 0.25, 0.15, 0.05)

RECORD_SCHEMA: dict[str, str] = {
    # identity -- decision-bound, contemporaneous, versioned
    "decision_id": "str, unique per decision",
    "captured_at": "ISO timestamp, written at the moment of decision",
    "model_id": "str, which model decided",
    "model_version": "str, the version in force",
    "schema_version": "str, the record schema in force",
    "policy_version": "str, the policy in force",
    # performance_per_decision
    "decision": "APPROVED | DENIED",
    "confidence": "float 0-1, the value the model returned",
    "latency_ms": "float, end to end",
    "error": "bool, did the call fail to answer",
    # data_quality_50
    "dq_null_ct": "int, required fields empty on the input",
    "dq_range_viol": "int, values outside plausible bounds",
    "dq_schema_ok": "bool, are the fields the ones we agreed",
    # security_authz_50
    "caller_id": "str, who asked",
    "auth_result": "bool, did the caller authenticate",
    "policy_violation": "bool, did the request breach a rule",
    # raw material for windowed measures
    "input_features": "list[float], for drift windows",
    "group": "A|B|C|D, for fairness windows -- never shown to the model",
    # integrity
    "checksum": "sha256 over the other fields, for detecting corruption in transit",
}

_REQUIRED = tuple(k for k in RECORD_SCHEMA if k != "checksum")


@dataclass(frozen=True)
class TelemetryConfig:
    """Everything the generator needs. Declared, so a run is reproducible."""

    n: int = STREAM_LENGTH
    drift_start: int = DRIFT_START
    seed: int = DEFAULT_SEED
    model_id: str = "credit_decisioning"
    model_version: str = "3.2"
    schema_version: str = "2.1"
    policy_version: str = "credit_policy_2026_04"
    start_at: str = "2026-09-10T09:00:00+00:00"


# ---------------------------------------------------------------------------
# Demo data generation. Nothing below is a production assumption.
# ---------------------------------------------------------------------------
def gen_applicants(n: int, rng: np.random.Generator, drifted: bool = False):
    """Synthetic loan applicants.

    With ``drifted=True`` incomes shift up, debt ratios climb, and the shift falls
    hardest on groups C and D. The disparity is injected on purpose so the
    fairness measure has something to detect.
    """
    income = rng.lognormal(11.0 + (0.30 if drifted else 0.0), 0.45, n)
    dti = rng.beta(2, 6, n) * (1.7 if drifted else 1.0)
    hist = rng.integers(0, 25, n)
    defaults = rng.poisson(0.9 if drifted else 0.25, n)
    amount = rng.lognormal(10.2, 0.6, n)
    group = rng.choice(["A", "B", "C", "D"], n, p=[0.40, 0.28, 0.18, 0.14])
    offset = {
        "A": 0.0,
        "B": -0.01,
        "C": -0.24 if drifted else -0.03,
        "D": -0.38 if drifted else -0.05,
    }
    income = income * np.array([1 + offset[g] for g in group])
    X = np.column_stack([np.log(income), dti, hist, defaults, np.log(amount)])
    return X, group


def _true_labels(X: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    z = (
        5.5 * (X[:, 0] - 11)
        - 8.0 * (X[:, 1] - 0.25)
        + 0.16 * (X[:, 2] - 12)
        - 2.2 * X[:, 3]
        - 0.5 * (X[:, 4] - 10.2)
        + 1.8
    )
    p = 1 / (1 + np.exp(-z))
    return (rng.random(len(p)) < p).astype(int)


def train_reference_model(cfg: TelemetryConfig = TelemetryConfig()):
    """Train the demo model. Returns (model, reference_means, reference_stds).

    The reference distribution is saved at training time because drift is
    measured against it.
    """
    from sklearn.linear_model import LogisticRegression

    rng = np.random.default_rng(cfg.seed)
    X_train, _ = gen_applicants(5000, rng)
    y_train = _true_labels(X_train, rng)
    model = LogisticRegression(max_iter=1000).fit(X_train, y_train)
    return model, X_train.mean(axis=0), X_train.std(axis=0)


# ---------------------------------------------------------------------------
# Emitting and validating records. This half is reusable.
# ---------------------------------------------------------------------------
def checksum(record: dict[str, Any]) -> str:
    """SHA-256 over every field except the checksum itself.

    This detects corruption and accidental edits. It is not a signature: anyone
    holding the record can recompute it, so it does not establish who wrote the
    record or that it has not been deliberately rewritten. Signing would need a
    key this example does not have.
    """
    body = {k: v for k, v in record.items() if k != "checksum"}
    payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()[:16]


def emit_record(
    x_row: np.ndarray,
    group: str,
    decision_num: int,
    model,
    rng: np.random.Generator,
    cfg: TelemetryConfig = TelemetryConfig(),
    degrade_dq: bool = False,
) -> dict[str, Any]:
    """Score one applicant and build the decision record for it.

    Latency, error rate, null rate, auth result and caller mix are generated here
    because there is no serving stack behind the notebook.
    """
    proba = float(model.predict_proba(x_row.reshape(1, -1))[0, 1])
    confidence = max(proba, 1 - proba)

    null_p = 0.06 if degrade_dq else 0.006
    null_ct = int(rng.random() < null_p) + int(rng.random() < null_p / 3)
    range_viol = sum(
        1 for v, (lo, hi) in zip(x_row, RANGES.values()) if not lo <= v <= hi
    )

    caller = CALLERS[int(rng.choice(4, p=_CALLER_SHARE))]
    if 800 <= decision_num < 850 and rng.random() < 0.55:
        caller = "svc_d"  # the burst: authenticated, authorised, 30x normal volume

    record = {
        "decision_id": f"DEC-{decision_num:05d}",
        "captured_at": (
            datetime.fromisoformat(cfg.start_at) + timedelta(minutes=decision_num)
        ).isoformat(),
        "model_id": cfg.model_id,
        "model_version": cfg.model_version,
        "schema_version": cfg.schema_version,
        "policy_version": cfg.policy_version,
        "decision": "APPROVED" if proba >= 0.5 else "DENIED",
        "confidence": round(confidence, 3),
        "latency_ms": round(float(rng.normal(180, 35)), 1),
        "error": bool(rng.random() < 0.004),
        "dq_null_ct": int(null_ct),
        "dq_range_viol": int(range_viol),
        "dq_schema_ok": bool(rng.random() > 0.002),
        "caller_id": caller,
        "auth_result": bool(rng.random() > 0.005),
        "policy_violation": bool(rng.random() < 0.001),
        "input_features": [round(float(v), 4) for v in x_row],
        "group": str(group),
    }
    record["checksum"] = checksum(record)
    return record


def validate_record(record: dict[str, Any], verify_checksum: bool = True) -> None:
    """Raise ValueError if the record is unusable as evidence."""
    missing = [f for f in _REQUIRED if f not in record]
    if missing:
        raise ValueError(f"record {record.get('decision_id')}: missing {missing}")
    if not 0.0 <= record["confidence"] <= 1.0:
        raise ValueError(f"record {record['decision_id']}: confidence out of range")
    if record["decision"] not in ("APPROVED", "DENIED"):
        raise ValueError(f"record {record['decision_id']}: unknown decision")
    if record["group"] not in ("A", "B", "C", "D"):
        raise ValueError(f"record {record['decision_id']}: unknown group")
    if verify_checksum:
        if "checksum" not in record:
            raise ValueError(f"record {record['decision_id']}: no checksum")
        expected = checksum(record)
        if record["checksum"] != expected:
            raise ValueError(
                f"record {record['decision_id']}: checksum mismatch "
                f"({record['checksum']} != {expected}); the record has been altered "
                f"or corrupted since it was written"
            )


def generate_stream(cfg: TelemetryConfig = TelemetryConfig()):
    """Generate the demo stream: healthy, then drifted from ``cfg.drift_start``."""
    model, ref_means, ref_stds = train_reference_model(cfg)
    rng = np.random.default_rng(cfg.seed)
    n_healthy = cfg.drift_start
    n_drifted = cfg.n - cfg.drift_start
    X_h, g_h = gen_applicants(n_healthy, rng)
    X_d, g_d = gen_applicants(n_drifted, rng, drifted=True)
    X = np.vstack([X_h, X_d])
    g = np.concatenate([g_h, g_d])

    records = [
        emit_record(X[i], g[i], i, model, rng, cfg, degrade_dq=(i >= cfg.drift_start))
        for i in range(cfg.n)
    ]
    for r in records:
        validate_record(r)
    return records, ref_means, ref_stds


# ---------------------------------------------------------------------------
# The sink. A JSON Lines file here; an append-only store in production.
# ---------------------------------------------------------------------------
def write_jsonl(records: Iterable[dict[str, Any]], path: Path | str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return p


def read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"No telemetry at {p}. Run 01_telemetry.ipynb first.")
    with p.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def reference_distribution_path(data_dir: Path | str = "data") -> Path:
    """Prefer a locally generated reference over the committed one.

    Notebook 1 writes the generated file when it retrains, so Notebooks 2 and 3
    measure drift against the same reference the telemetry came from. With no
    local run they fall back to the committed file, which lets them run alone.
    """
    d = Path(data_dir)
    generated = d / GENERATED_REFERENCE
    return generated if generated.exists() else d / COMMITTED_REFERENCE


def reference_distribution(path: Path | str) -> tuple[np.ndarray, np.ndarray]:
    raw = json.loads(Path(path).read_text())
    return np.array(raw["means"]), np.array(raw["stds"])


def write_reference_distribution(
    means: np.ndarray, stds: np.ndarray, path: Path | str
) -> Path:
    """Write a reference distribution. Refuses to overwrite the committed file."""
    p = Path(path)
    if p.name == COMMITTED_REFERENCE:
        raise ValueError(
            f"{COMMITTED_REFERENCE} is a committed input and must not be written by "
            f"a run. Write {GENERATED_REFERENCE} instead."
        )
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(
        {"features": list(FEATURES), "means": list(map(float, means)),
         "stds": list(map(float, stds))}, indent=2) + "\n")
    return p


def newest_capture(records: Sequence[dict[str, Any]]) -> datetime:
    return max(parse_utc(r["captured_at"]) for r in records)
