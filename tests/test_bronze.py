"""Raw-NEMSIS bronze (the mapper's ONE Delta table, ADR-009): land, dedupe,
and replay-to-identical-FHIR. Skipped unless the `bronze` extra is installed."""

import glob

import pytest

deltalake = pytest.importorskip("deltalake")

from nemsis2fhir.convert import convert  # noqa: E402
from nemsis2fhir.ingest.bronze import land, replay  # noqa: E402

from .conftest import CHEST_PAIN, FIXTURES  # noqa: E402


def test_land_corpus_and_dedupe(tmp_path):
    table = tmp_path / "bronze"
    total = sum(land(path, table) for path in sorted(FIXTURES.glob("*.xml")))
    assert total == 6  # one row per PCR across the corpus
    # Idempotent by file hash: a second sweep lands nothing.
    again = sum(land(path, table) for path in sorted(FIXTURES.glob("*.xml")))
    assert again == 0
    rows = deltalake.DeltaTable(str(table)).to_pyarrow_table()
    assert rows.num_rows == 6
    assert set(rows.column("agency_number").to_pylist()) == {"4901"}
    assert all(v == "3.5.0" for v in rows.column("nemsis_version").to_pylist())


def test_replay_reproduces_identical_fhir(tmp_path):
    """The audit/replay guarantee: a bronze row converts to byte-identical
    resources (same deterministic ids, same content) as the original file."""
    table = tmp_path / "bronze"
    land(CHEST_PAIN, table)
    payloads = replay(table, pcr_number="PCR-2026-000123")
    assert len(payloads) == 1

    replayed = convert(payloads[0])[0]  # XSD-validates the reconstructed doc
    original = convert(CHEST_PAIN)[0]
    assert replayed.resources == original.resources
    assert replayed.document == original.document


def test_replay_filter_unknown_pcr(tmp_path):
    table = tmp_path / "bronze"
    land(CHEST_PAIN, table)
    assert replay(table, pcr_number="PCR-NOPE") == []
