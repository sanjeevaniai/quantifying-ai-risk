"""Record emission, validation and the integrity checksum."""

from __future__ import annotations

import pytest

from qair.telemetry import checksum, read_jsonl, validate_record, write_jsonl


def test_every_fixture_record_validates(records):
    for r in records:
        validate_record(r)


def test_checksum_covers_the_record_contents(records):
    r = dict(records[0])
    assert r["checksum"] == checksum(r)


def test_an_altered_record_fails_validation(records):
    altered = dict(records[0], confidence=0.123)
    with pytest.raises(ValueError, match="checksum mismatch"):
        validate_record(altered)


def test_a_record_without_a_checksum_is_rejected(records):
    stripped = {k: v for k, v in records[0].items() if k != "checksum"}
    with pytest.raises(ValueError, match="no checksum"):
        validate_record(stripped)


def test_checksum_verification_can_be_skipped(records):
    """Useful when reading records written by a system that checksums differently."""
    altered = dict(records[0], confidence=0.123)
    validate_record(altered, verify_checksum=False)


def test_the_checksum_is_not_treated_as_a_signature():
    """Anyone holding a record can recompute the checksum, so it detects
    corruption but does not establish authorship."""
    record = {"decision_id": "DEC-1", "confidence": 0.9}
    record["checksum"] = checksum(record)
    forged = dict(record, confidence=0.1)
    forged["checksum"] = checksum(forged)
    validate_record  # the value is recomputable without a key
    assert forged["checksum"] != record["checksum"]
    assert forged["checksum"] == checksum(forged)


def test_round_trip_through_jsonl(records, tmp_path):
    path = write_jsonl(records[:10], tmp_path / "sample.jsonl")
    assert read_jsonl(path) == records[:10]


def test_missing_stream_raises_a_useful_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="01_telemetry"):
        read_jsonl(tmp_path / "nothing.jsonl")
