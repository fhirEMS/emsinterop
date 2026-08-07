"""Conversion issue log ↔ fhirEngine dead-letter reconciliation (Roadmap P5).

fhirEngine dead-letters any resource that fails pre-Bronze validation into an
append-only Delta table at <FHIRENGINE_DELTA_BASE>/deadletter/<resourcetype>
with rows {id, resourceType, error, body_json, failed_at}. This module READS
those tables — ADR-009 forbids *writing* FHIR storage, not observing it — and
joins the rows back to the PCRs this mapper produced, merging them with the
conversion issue log into one gap-register feed per sweep.

Two join keys, in order:
  1. the resource id (our deterministic UUIDv5, so a dead-lettered row's id
     is stable across resubmissions), and
  2. the `urn:nemsis:identifier:pcr` business identifier inside body_json
     (covers rows whose id we no longer produce, e.g. after a mapper change).

Note the client-side half: a transaction Bundle rejected at pre-validation is
refused ATOMICALLY and never dead-lettered, so those failures only exist in
the OperationOutcome returned at submit time — captured via
issues_from_operation_outcome() in emsinterop.issues.

Requires the optional `bronze` extra (deltalake), imported lazily.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .issues import IssueLog
from .terminology import systems


def _pcr_number_from_body(body: dict) -> str | None:
    """Pull the PCR business identifier out of a dead-lettered resource body.

    Encounter carries it in identifier[] (list); Composition.identifier is a
    single Identifier object in R4."""
    identifier = body.get("identifier")
    if isinstance(identifier, dict):
        identifier = [identifier]
    for entry in identifier or []:
        if entry.get("system") == systems.PCR_ID and entry.get("value"):
            return entry["value"]
    return None


def dead_letter_rows(delta_base: str | Path) -> list[dict]:
    """Read every deadletter/<resourcetype> Delta table under a fhirEngine
    delta base into normalized rows:
    {resource_type, id, error, failed_at, pcr_number (from body_json, or None)}.
    """
    try:
        from deltalake import DeltaTable
    except ImportError as error:  # pragma: no cover
        raise RuntimeError(
            "dead-letter reconciliation requires the 'bronze' extra: "
            "pip install emsinterop[bronze]"
        ) from error

    root = Path(delta_base) / "deadletter"
    rows: list[dict] = []
    if not root.is_dir():
        return rows
    for table_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        try:
            table = DeltaTable(str(table_dir)).to_pyarrow_table()
        except Exception:
            continue  # not a Delta table (stray dir) — nothing to reconcile
        cols = {name: table.column(name).to_pylist() for name in table.column_names}
        for i in range(table.num_rows):
            body = {}
            raw = cols.get("body_json", [None] * table.num_rows)[i]
            if raw:
                try:
                    body = json.loads(raw)
                except (TypeError, ValueError):
                    pass
            rows.append({
                "resource_type": cols.get("resourceType", [table_dir.name] * table.num_rows)[i],
                "id": cols.get("id", [None] * table.num_rows)[i],
                "error": cols.get("error", [None] * table.num_rows)[i],
                "failed_at": cols.get("failed_at", [None] * table.num_rows)[i],
                "pcr_number": _pcr_number_from_body(body),
            })
    return rows


def gap_register(
    conversions: Iterable[tuple[str | None, list[str], IssueLog]],
    dead_letter: list[dict],
) -> dict:
    """Join dead-letter rows to conversions and merge with their issue logs.

    `conversions` yields (pcr_number, resource_ids, issue_log) per PCR — the
    shape ConversionResult provides via conversion_key(). Output is the
    gap-register feed: per-PCR issues + dead-lettered resources, plus any
    dead-letter rows no known PCR accounts for.
    """
    pcrs: list[dict] = []
    claimed: set[int] = set()
    for pcr_number, resource_ids, issues in conversions:
        ids = set(resource_ids)
        mine = []
        for index, row in enumerate(dead_letter):
            if index in claimed:
                continue
            if row["id"] in ids or (pcr_number and row["pcr_number"] == pcr_number):
                mine.append(row)
                claimed.add(index)
        pcrs.append({
            "pcr_number": pcr_number,
            "resource_count": len(resource_ids),
            "issues": issues.to_dicts(),
            "dead_letter": mine,
        })
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pcrs": pcrs,
        "unmatched_dead_letter": [
            row for index, row in enumerate(dead_letter) if index not in claimed
        ],
    }


def reconcile_bronze(bronze_table: str | Path, delta_base: str | Path) -> dict:
    """The full sweep: replay every PCR from raw-NEMSIS bronze, re-convert,
    and reconcile against fhirEngine's dead-letter tables."""
    from .convert import convert
    from .ingest.bronze import replay

    conversions: list[tuple[str | None, list[str], IssueLog]] = []
    for payload in replay(bronze_table):
        for result in convert(payload):
            conversions.append((
                result.context.pcr_number,
                [r["id"] for r in result.resources],
                result.issues,
            ))
    return gap_register(conversions, dead_letter_rows(delta_base))
