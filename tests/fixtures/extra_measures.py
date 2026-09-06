"""A measurement function for the add-a-measure integration test.

Written the way a contributor would write one: take the records and the contract,
read any constants from the contract, and return one Observation per window.
"""

from __future__ import annotations

import numpy as np

from qair.evidence import Observation
from qair.timeutil import parse_utc


def latency_tail_50(records, contract, **_):
    limit = contract.param("max_latency_ms")
    length = contract.window_length
    out = []
    for start in range(0, len(records) - length + 1, length):
        window = records[start : start + length]
        share = float(np.mean([r["latency_ms"] <= limit for r in window]))
        out.append(
            Observation(
                measure_id=contract.measure_id,
                evidence_type=contract.evidence_type,
                passed=share >= contract.threshold,
                observed_at=parse_utc(window[-1]["captured_at"]),
                statistic=share,
                window_index=start // length,
            )
        )
    return out
